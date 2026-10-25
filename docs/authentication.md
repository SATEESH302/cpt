# FE-003 patient authentication

Frontend files remain directly in `D:\CPT-FE`. The matching backend is `D:\cpt`. FE-003 adds real authentication to that backend; it does not use the unrelated `D:\CTP` project or simulate identity in the browser.

## Endpoints and schemas

The following routes are registered in all environments under the configured API prefix (default `/api/v1`). All auth responses, including errors, use `Cache-Control: no-store`.

| Method | Path | Input | Response / behavior |
| --- | --- | --- | --- |
| GET | `/api/v1/auth/csrf` | None | `{ csrf_token }`; sets a short-lived HttpOnly pre-auth nonce cookie |
| POST | `/api/v1/auth/register` | `RegistrationRequest`; Origin and X-CSRF-Token | 201 `{ message }`; atomic patient and credential creation; no automatic login |
| POST | `/api/v1/auth/login` | `{ identifier, password }`; Origin and X-CSRF-Token | `{ user, csrf_token, expires_at }`; rotates the opaque session cookie |
| GET | `/api/v1/auth/me` | Session cookie only | Same safe session/profile projection; 401 without a valid, unexpired server session |
| POST | `/api/v1/auth/logout` | `{}`; session cookie, Origin, session-bound X-CSRF-Token | `{ message }`; deletes the server session and clears cookies |

`RegistrationRequest` fields: `full_name` (trimmed, 1–150), `phone` (7–20 characters, 7–15 digits with optional leading + and separators), `email` (validated, normalized lowercase, max 255), `password` (12–128 characters, not trimmed), `terms_accepted` (strict true), optional `gender` (1–20) and `date_of_birth` (valid MySQL date, year >=1000, not future). Unknown fields are forbidden. The frontend's Zod schema additionally verifies `confirmPassword`, which is never sent to the backend. Empty optional fields become null. Use country codes consistently: phone matching removes formatting separators but does not infer a country for a national number.

Login accepts registered email (case-insensitive) or the registered mobile digits with formatting separators. Wrong passwords and unknown accounts return the same generic 401. Registration conflicts return a generic 409 without identifying the matching contact. Invalid payloads use the existing sanitized 422 contract; throttled attempts return 429.

`user` contains only `patient_id`, `full_name`, `email`, `phone`, `gender`, `date_of_birth`, and `role: "patient"`. `/me` obtains the patient ID from the database session, never from browser-supplied identity. Hashes and session IDs are not returned as JSON. Existing patient-management response schemas remain unchanged.

## Database changes

Alembic revision `0002_patient_auth`, following the existing verified baseline `0001_existing_schema`, adds:

- `patient_credentials`: one-to-one patient foreign-key/primary-key, unique normalized login email and mobile digits, Argon2id password hash, terms acceptance timestamp.
- `auth_sessions`: SHA-256 digest of a random 256-bit opaque session ID, patient foreign key, absolute UTC expiry.
- `auth_rate_limits`: hashed counter key, attempts, window reset time. Atomic MySQL upserts share limits across workers.

The original `patients` table is reused without changing its columns. No existing patient is silently claimed or overwritten. A registration matching an existing patient's contact is rejected; legacy patient records require a future verified account-enrollment/recovery flow. Credential login identifiers are maintained separately from the profile; changing a profile through development-only management is not an account-identifier change flow.

The migration only creates new tables. It does not seed, reset, merge, or delete patient data. Its downgrade deliberately refuses account/session data destruction. The schema verifier understands both the original ten-table baseline and the thirteen-table authenticated schema.

After reviewing and backing up your **local development** database, apply using Alembic from the backend directory:

```powershell
cd D:\cpt
$env:DEBUG = 'false'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
```

If no Alembic revision has been recorded yet, the existing guard first verifies the original schema before adopting the baseline. Schema drift fails safely; do not stamp over drift or reset the database. Never apply these commands to a production/shared database as part of testing.

## Browser and session lifecycle

The Axios instance sends cookie credentials. Registration and login obtain a new nonce from `/auth/csrf`, then send it in `X-CSRF-Token` alongside the HttpOnly nonce cookie. The backend requires an exact allowlisted Origin and application/json for these requests, including login (login CSRF protection). Authenticated logout requires a token derived from the validated opaque session with domain-separated SHA-256, delivered through `/me`, and the same Origin check. Cross-origin scripts cannot read CSRF JSON unless explicitly allowed by CORS. The session cookie is never read by JavaScript.

`AuthProvider` restores the current user through `/me` on reload, exposes login/logout/refresh and loading state, and revalidates on window focus. Login succeeds only after the backend login and authorized `/me` calls succeed. ProtectedRoute waits during restoration, redirects anonymous visitors to login with their intended dashboard destination, and checks the returned patient role. It shows retry on a backend failure instead of granting access. Request 401 events and the server-provided expiration time clear the profile and return the visitor to login without retry/redirect loops. Failed network logout reports an error and retains the current profile rather than pretending the server session was invalidated.

No authentication secrets are written to localStorage or sessionStorage. A CSRF token is kept only in module memory. No patient data is stored persistently by the frontend. The patient dashboard uses only the authorized profile and labels prescription uploads, bookings, and reports Coming Soon.

## Security configuration and deployment requirements

Passwords use the maintained [argon2-cffi Argon2id hasher](https://argon2-cffi.readthedocs.io/en/stable/api.html), random salts, and rehash-on-login when parameters change. Session design and CSRF defenses follow the [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html); SameSite is an additional defense, alongside explicit CSRF checks.

Development/test cookies are named `dtp_session` and `dtp_csrf`, HttpOnly, host-only, Path=/, SameSite=Lax, with Secure disabled **only** for local HTTP. Staging/production use `__Host-` names and mandatory Secure cookies; writes require HTTPS and an HTTPS allowlisted Origin. There is no environment setting that disables production Secure cookies. Debug responses are disabled outside development/test.

CORS now enables credentials only with the existing explicit origin list and permits `X-CSRF-Token`. Use `http://localhost:5173` with `http://localhost:8000` consistently during development. Mixing localhost and 127.0.0.1 breaks same-site cookie assumptions. In production, use same-site HTTPS frontend/API hosts (for example app.example.com and api.example.com), explicitly allow the frontend origin, and configure trusted proxy headers correctly. The Lax policy intentionally does not support unrelated cross-site hosting; use same-site custom domains or a same-origin API proxy. Do not change cookies to insecure settings to accommodate deployment.

Configuration defaults (backend environment only):

```env
AUTH_SESSION_SECONDS=3600
AUTH_RATE_WINDOW_SECONDS=900
AUTH_LOGIN_ATTEMPTS=10
AUTH_IP_ATTEMPTS=50
```

Sessions have an absolute expiry of one hour by default, across restarts/workers. Every login rotates the current browser session. Logout deletes its database record, making replay fail. Other devices' sessions are not revoked by a single-device logout. Login limits apply both per normalized account and client IP; registration is limited per IP using AUTH_LOGIN_ATTEMPTS. Rate counters do not store plain account/IP identifiers. Session/rate-limit expiration checks are enforced even before cleanup. Schedule deletion of expired `auth_sessions` and old `auth_rate_limits` records as database maintenance. Add deployment-level abuse protection and trust forwarded client IPs only from your own proxy.

Existing FE-002 management routes remain local-development-only and are not administrator authentication. They remain absent from staging/production. Patient login does not authorize public patient listing or administrative writes. Backend authorization must be added for any future administrator functionality.

Before a public launch, provide reviewed production Terms and Conditions/privacy content (the current UI contains short starter terms), verified account enrollment/contact verification and password recovery, HTTPS/same-site domains, restricted proxy/CORS settings, and a documented database backup/migration plan. Do not expose development servers or real patient data publicly. These are deployment requirements, not claims of features implemented in FE-003.

## Tests and verification limits

Frontend tests mock real auth schemas and cover field rendering/validation, email, confirmation, registration/conflict, login/failure, duplicate submissions, restoration, protected routing, profile rendering, logout/failure, session expiry, unsupported roles, and backend downtime/retry. Service tests verify CSRF headers and cookie configuration.

Backend tests use a private SQLite database for HTTP/service/session tests, including hashing, duplicate contacts, legacy-patient non-claiming, rotation, generic credential errors, expiration, cross-patient prevention, CSRF, production cookie policy and credentialed CORS. Existing regression tests are retained and updated for the additive schema/API contract. Migration tests check preservation of an existing row and refusal of destructive downgrade.

An additional opt-in test creates a uniquely named temporary local MySQL schema, builds the original empty schema, applies Alembic, verifies the final metadata, and exercises registration/login/me/logout/replay prevention. It removes only its own `cpt_auth_test_<uuid>` schema afterward. It never copies or modifies real patient records. Running it requires an account allowed to create/drop that test schema:

```powershell
cd D:\cpt
$env:DEBUG = 'false'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest -q

# Optional isolated MySQL verification:
$env:RUN_AUTH_MYSQL_TESTS = '1'
$env:AUTH_MYSQL_ENV_FILE = 'D:\cpt\.env'
.\.venv\Scripts\python.exe -B -m pytest tests/test_auth_mysql.py -q
```

The MySQL auth lifecycle and migration passed in the disposable schema. That result does not imply that an existing database has already been migrated. See the final handoff for whether the local development migration was applied. No production/shared records are mutated during tests. Visual browser QA was unavailable; DOM behavior and HTTP contracts are tested.
