"""Full auth HTTP/service/DB tests on an isolated, disposable SQLite database."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, DefaultClause, Integer, MetaData, create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.session import get_db
from app.models.auth import AuthRateLimit, AuthSession, PatientCredential
from app.models.patient import Patient
from app.services.auth import digest, hasher, utcnow

ORIGIN = {"Origin": "http://localhost:5173"}
PAYLOAD = {"full_name": "Auth Test Patient", "phone": "+91 9876543210", "email": "auth@example.com", "password": "a long test password", "terms_accepted": True}


@pytest.fixture
def auth_app():
    from app.main import create_app
    metadata = MetaData()
    patient = Patient.__table__.to_metadata(metadata)
    patient.c.patient_id.type = BigInteger().with_variant(Integer, "sqlite")
    patient.c.updated_at.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    for model in (PatientCredential, AuthSession, AuthRateLimit):
        model.__table__.to_metadata(metadata)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    application = create_app(Settings(_env_file=None, app_env="test", debug=False))
    def isolated_db():
        with factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise
    application.dependency_overrides[get_db] = isolated_db
    yield application, factory
    engine.dispose()


@pytest.fixture
def auth_client(auth_app):
    with TestClient(auth_app[0], raise_server_exceptions=False) as client:
        yield client


def post(client, path, payload, **headers):
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    return client.post("/api/v1/auth/" + path, json=payload, headers={**ORIGIN, "X-CSRF-Token": token, **headers})


def register(client, **changes):
    return post(client, "register", {**PAYLOAD, **changes})


def login(client, identifier=PAYLOAD["email"], password=PAYLOAD["password"]):
    return post(client, "login", {"identifier": identifier, "password": password})


def test_registration_hashing_relationship_and_safe_response(auth_client, auth_app):
    response = register(auth_client)
    assert response.status_code == 201, response.text
    assert response.json() == {"message": "Registration successful. Please log in."}
    assert response.headers["cache-control"] == "no-store"
    with auth_app[1]() as db:
        credential = db.scalar(select(PatientCredential))
        assert credential.password_hash.startswith("$argon2id$")
        assert hasher.verify(credential.password_hash, PAYLOAD["password"])
        assert credential.patient.full_name == PAYLOAD["full_name"]
        assert credential.patient.credential.patient_id == credential.patient_id
        assert credential.phone == "919876543210"
        assert credential.terms_accepted_at is not None


@pytest.mark.parametrize("changes", [{"email": "AUTH@EXAMPLE.COM", "phone": "9876543211"}, {"email": "other@example.com", "phone": "+91 (98765) 43210"}])
def test_duplicate_contacts_never_create_a_second_patient(auth_client, auth_app, changes):
    assert register(auth_client).status_code == 201
    response = register(auth_client, **changes)
    assert response.status_code == 409
    assert PAYLOAD["email"] not in response.text
    with auth_app[1]() as db:
        assert len(db.scalars(select(Patient)).all()) == 1


def test_existing_patient_is_not_claimed_or_duplicated(auth_client, auth_app):
    with auth_app[1]() as db:
        db.add(Patient(full_name="Legacy", phone="+91 9876543210"))
        db.commit()
    assert register(auth_client).status_code == 409
    with auth_app[1]() as db:
        assert db.scalar(select(PatientCredential)) is None
        assert db.scalar(select(Patient)).full_name == "Legacy"


@pytest.mark.parametrize("changes", [{"email": "invalid"}, {"phone": "abc"}, {"password": "short"}, {"password": "x" * 129}, {"terms_accepted": False}, {"terms_accepted": 1}, {"date_of_birth": "2999-01-01"}, {"patient_id": 2}, {"confirmPassword": "private"}])
def test_registration_validation(auth_client, changes):
    response = register(auth_client, **changes)
    assert response.status_code == 422
    assert "private" not in response.text


def test_login_me_mobile_and_rotation(auth_client, auth_app):
    register(auth_client)
    response = login(auth_client)
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "patient"
    assert response.json()["user"]["full_name"] == PAYLOAD["full_name"]
    token = auth_client.cookies.get("dtp_session")
    cookie = response.headers.get_list("set-cookie")[0]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=3600" in cookie
    with auth_app[1]() as db:
        assert db.get(AuthSession, digest(token)) is not None
        assert db.get(AuthSession, token) is None
    assert auth_client.get("/api/v1/auth/me").json() == response.json()
    assert login(auth_client, identifier="+91 (98765) 43210").status_code == 200
    with auth_app[1]() as db:
        assert db.get(AuthSession, digest(token)) is None


def test_invalid_password_and_unknown_account_are_generic(auth_client):
    register(auth_client)
    wrong = login(auth_client, password="wrong password")
    unknown = login(auth_client, identifier="missing@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"] == unknown.json()["error"]
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_logout_invalidates_session_and_cookie(auth_client):
    register(auth_client)
    payload = login(auth_client).json()
    stolen = auth_client.cookies.get("dtp_session")
    response = auth_client.post("/api/v1/auth/logout", json={}, headers={**ORIGIN, "X-CSRF-Token": payload["csrf_token"]})
    assert response.status_code == 200
    assert auth_client.cookies.get("dtp_session") is None
    auth_client.cookies.set("dtp_session", stolen)
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_expiration_and_cross_patient_access(auth_client, auth_app):
    register(auth_client)
    first = login(auth_client).json()["user"]
    register(auth_client, email="second@example.com", phone="9876543211", full_name="Second")
    other_id = login(auth_client, identifier="second@example.com").json()["user"]["patient_id"]
    login(auth_client)
    response = auth_client.get("/api/v1/auth/me", params={"patient_id": other_id})
    assert response.json()["user"] == first
    assert set(response.json()["user"]) == {"patient_id", "full_name", "email", "phone", "gender", "date_of_birth", "role"}
    with auth_app[1]() as db:
        session = db.get(AuthSession, digest(auth_client.cookies.get("dtp_session")))
        session.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_csrf_missing_wrong_origin_and_token_rejected(auth_client):
    assert auth_client.post("/api/v1/auth/register", json=PAYLOAD, headers=ORIGIN).status_code == 403
    assert post(auth_client, "register", PAYLOAD, Origin="https://evil.example").status_code == 403
    register(auth_client)
    login(auth_client)
    response = auth_client.post("/api/v1/auth/logout", json={}, headers={**ORIGIN, "X-CSRF-Token": "bad"})
    assert response.status_code == 403
    assert auth_client.get("/api/v1/auth/me").status_code == 200


def test_rate_limit_shared_in_database_and_no_plain_identifiers(auth_client, auth_app):
    for _ in range(10):
        assert login(auth_client, identifier="missing@example.com").status_code == 401
    response = login(auth_client, identifier="missing@example.com")
    assert response.status_code == 429
    with auth_app[1]() as db:
        rows = db.scalars(select(AuthRateLimit)).all()
        assert len(rows) == 2
        assert all(len(row.key_hash) == 64 and "missing" not in row.key_hash for row in rows)


def test_credentialed_cors_and_production_cookie_policy(auth_client, auth_app):
    preflight = auth_client.options("/api/v1/auth/login", headers={**ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-csrf-token"})
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-credentials"] == "true"
    assert preflight.headers["access-control-allow-origin"] == ORIGIN["Origin"]
    settings = Settings(_env_file=None, app_env="production")
    assert settings.auth_secure_cookies
    assert settings.auth_cookie_name.startswith("__Host-")
    auth_app[0].state.settings = settings
    response = auth_client.get("/api/v1/auth/csrf")
    assert "Secure" in response.headers["set-cookie"]
    assert auth_client.post("/api/v1/auth/login", json={}, headers=ORIGIN).status_code == 403


def test_auth_logs_never_contain_password_or_session(auth_client, capsys):
    register(auth_client)
    login(auth_client)
    token = auth_client.cookies.get("dtp_session")
    auth_client.get("/api/v1/auth/me")
    output = capsys.readouterr().out
    assert PAYLOAD["password"] not in output
    assert token not in output


def test_production_https_login_uses_host_cookie_and_restores_session(auth_app):
    auth_app[0].state.settings = Settings(_env_file=None, app_env="production", cors_origins=["https://app.example.test"])
    with TestClient(auth_app[0], base_url="https://api.example.test") as client:
        assert post(client, "register", PAYLOAD, Origin="https://app.example.test").status_code == 201
        response = post(client, "login", {"identifier": PAYLOAD["email"], "password": PAYLOAD["password"]}, Origin="https://app.example.test")
        assert response.status_code == 200
        assert client.cookies.get("__Host-dtp_session")
        assert "Secure" in response.headers.get_list("set-cookie")[0]
        assert client.get("/api/v1/auth/me").status_code == 200
