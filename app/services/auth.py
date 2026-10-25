"""Argon2id accounts, durable throttling, and database-backed opaque sessions."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.models.auth import AuthRateLimit, AuthSession, PatientCredential
from app.models.patient import Patient
from app.schemas.auth import RegistrationRequest, normalized_phone

hasher = PasswordHasher()  # Maintained Argon2id defaults, independent random salts.
dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def session_csrf(token: str) -> str:
    return digest("csrf:" + token)


def invalid_credentials() -> ApplicationError:
    return ApplicationError("INVALID_CREDENTIALS", "Invalid email/mobile or password.", 401)


class AuthService:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.settings = db, settings

    def throttle(self, key: str, limit: int) -> None:
        """Atomic upsert: works across workers, counters contain no raw identifiers."""
        now = utcnow()
        table = AuthRateLimit.__table__
        expired = table.c.resets_at <= now
        insert = mysql_insert if self.db.bind.dialect.name == "mysql" else sqlite_insert
        statement = insert(table).values(
            key_hash=digest(key), attempts=1,
            resets_at=now + timedelta(seconds=self.settings.auth_rate_window_seconds),
        )
        changes = dict(
            attempts=case((expired, 1), else_=table.c.attempts + 1),
            resets_at=case((expired, now + timedelta(seconds=self.settings.auth_rate_window_seconds)), else_=table.c.resets_at),
        )
        if self.db.bind.dialect.name == "mysql":
            # MySQL evaluates assignments left-to-right: update attempts first.
            statement = statement.on_duplicate_key_update(list(changes.items()))
        else:
            statement = statement.on_conflict_do_update(index_elements=["key_hash"], set_=changes)
        self.db.execute(statement)
        count = self.db.scalar(select(AuthRateLimit.attempts).where(table.c.key_hash == digest(key)))
        self.db.commit()
        if count > limit:
            raise ApplicationError("RATE_LIMITED", "Too many attempts. Please try again later.", 429)

    def register(self, payload: RegistrationRequest) -> Patient:
        email, phone = str(payload.email).lower(), normalized_phone(payload.phone)
        normalized_column = Patient.phone
        for char in ("+", " ", "(", ")", "-"):
            normalized_column = func.replace(normalized_column, char, "")
        exists = self.db.scalar(select(Patient.patient_id).where(or_(
            func.lower(Patient.email) == email, normalized_column == phone
        )).limit(1))
        if exists is not None:
            # Do not silently claim or modify an existing patient, even without credentials.
            raise ApplicationError("REGISTRATION_CONFLICT", "Registration could not be completed with these contact details.", 409)
        password_hash = hasher.hash(payload.password)
        patient = Patient(
            **{**payload.model_dump(exclude={"password", "terms_accepted"}), "email": email}
        )
        self.db.add(patient)
        try:
            self.db.flush()
            self.db.add(PatientCredential(
                patient_id=patient.patient_id, email=email, phone=phone,
                password_hash=password_hash, terms_accepted_at=utcnow(),
            ))
            self.db.flush()
            self.db.refresh(patient)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ApplicationError("REGISTRATION_CONFLICT", "Registration could not be completed with these contact details.", 409) from None
        return patient

    def login(self, identifier: str, password: str, old_token: str | None) -> tuple[Patient, str, datetime]:
        identifier = identifier.lower().strip() if "@" in identifier else normalized_phone(identifier)
        self.throttle("login-account:" + identifier, self.settings.auth_login_attempts)
        column = PatientCredential.email if "@" in identifier else PatientCredential.phone
        credential = self.db.scalar(select(PatientCredential).where(column == identifier))
        try:
            hasher.verify(credential.password_hash if credential else dummy_hash, password)
        except (VerificationError, InvalidHashError):
            raise invalid_credentials() from None
        if credential is None:
            raise invalid_credentials()
        if hasher.check_needs_rehash(credential.password_hash):
            credential.password_hash = hasher.hash(password)
        patient = self.db.get(Patient, credential.patient_id)
        if patient is None:
            raise invalid_credentials()
        if old_token:
            self.db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(old_token)))
        token = secrets.token_urlsafe(32)
        expires = utcnow() + timedelta(seconds=self.settings.auth_session_seconds)
        self.db.add(AuthSession(token_hash=digest(token), patient_id=patient.patient_id, expires_at=expires))
        self.db.commit()
        return patient, token, expires

    def current(self, token: str | None) -> tuple[Patient, AuthSession]:
        if not token or len(token) > 128:
            raise ApplicationError("UNAUTHENTICATED", "Please log in to continue.", 401)
        session = self.db.get(AuthSession, digest(token))
        if session is None or session.expires_at <= utcnow():
            raise ApplicationError("SESSION_EXPIRED", "Your session has expired. Please log in again.", 401)
        patient = self.db.get(Patient, session.patient_id)
        if patient is None:
            raise ApplicationError("UNAUTHENTICATED", "Please log in to continue.", 401)
        return patient, session

    def logout(self, token: str) -> None:
        self.db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(token)))
        self.db.commit()
