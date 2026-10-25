"""Account credentials and hashed, revocable sessions; no patient table changes."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PatientCredential(Base):
    __tablename__ = "patient_credentials"

    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patients.patient_id", ondelete="CASCADE"),
        primary_key=True, autoincrement=False,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str] = mapped_column(String(15), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime)
    patient: Mapped["Patient"] = relationship(back_populates="credential")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patients.patient_id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    resets_at: Mapped[datetime] = mapped_column(DateTime)
