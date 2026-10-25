# FE-003 patient authentication

Patient authentication is now implemented with Argon2id credentials, database-backed opaque sessions, CSRF protection, and shared login throttling. See [authentication setup, migration and security notes](docs/authentication.md). The original management routers remain development-only. Apply the additive Alembic migration before using auth endpoints. Sections below describe earlier backend stories; statements that authentication is deferred are superseded by FE-003.

# Diagnostic Platform API

FastAPI backend for the Diagnostic Testing and Home Sample Collection Platform.
US-001 provides versioned routing, validated settings, public liveness, CORS,
centralized errors, request IDs, JSON logging, and OpenAPI documentation. US-002
adds SQLAlchemy connectivity, mappings for ten existing MySQL tables, session
management, read-only schema verification, and a guarded Alembic baseline.
US-003 adds local-development patient registration, retrieval, updates,
pagination, and search. US-004 adds local laboratory management and controlled
status changes. US-005 adds the common-price diagnostic catalog, negotiated
laboratory costs, test availability, and private margin comparisons.
Authentication and other business modules are deferred.

## Prerequisites and dependencies

Use Python **3.11** (verified with 3.11.7), standard-library `venv`, pip, and
MySQL 8.0 with the existing `diagnostic_platform` schema and its ten tables.
Initial installation requires PyPI access. No AWS account is needed.

Pinned dependencies include FastAPI 0.162.0, Uvicorn 0.54.0, Pydantic 2.14.1,
Pydantic Settings 2.16.1, SQLAlchemy 2.0.55, PyMySQL 1.2.3, Alembic 1.20.1,
pytest 9.1.1, HTTPX 0.28.1, and email-validator 2.3.0. PyMySQL's `rsa` extra provides cryptography
support for MySQL 8 authentication. Starlette 0.52.1 retains HTTPX TestClient
support. `requirements.txt` also pins transitive dependencies. No uv tooling is
required.

## Project structure

All project files live directly under `cpt/`. Python packages also include
`__init__.py`; `app/models/__init__.py` registers all ten mappings.

```text
cpt/
|-- app/
|   |-- main.py
|   |-- api/dependencies.py
|   |-- api/v1/{router.py,endpoints/{health,patients,laboratories}.py}
|   |-- api/v1/endpoints/{diagnostic_tests,laboratory_test_prices}.py
|   |-- core/{config,cors,exceptions,logging}.py
|   |-- db/{base,session,verification,__main__}.py
|   |-- models/
|   |   |-- patient.py
|   |   |-- laboratory.py
|   |   |-- diagnostic_test.py
|   |   |-- lab_test_price.py
|   |   |-- prescription.py
|   |   |-- booking.py
|   |   |-- booking_test.py
|   |   |-- sample_collection.py
|   |   |-- payment.py
|   |   `-- diagnostic_report.py
|   |-- schemas/{health,errors,common,patient,laboratory}.py
|   |-- schemas/catalog.py
|   |-- repositories/{patient,laboratory}.py
|   |-- repositories/catalog.py
|   |-- services/{patient,laboratory}.py
|   |-- services/catalog.py
|   `-- utils/
|-- alembic/
|   |-- env.py
|   |-- script.py.mako
|   `-- versions/0001_existing_schema.py
|-- tests/
|   |-- conftest.py
|   |-- test_{config,cors,docs,exceptions,health,logging}.py
|   |-- test_{database,migrations,models,mysql}.py
|   |-- test_{patients,patient_service}.py
|   |-- test_{laboratories,laboratory_service}.py
|   `-- test_{catalog,catalog_service}.py
|-- .env.example
|-- .gitignore
|-- alembic.ini
|-- pyproject.toml
|-- requirements.txt
|-- sql_scripts
`-- README.md
```

The patient and laboratory repositories handle ORM queries; services own business rules
and write transactions. Routes handle HTTP concerns, schemas validate responses,
and core/db provide shared
infrastructure. `create_app(settings)` supports isolated applications;
`app.main:app` exports the standard ASGI application.

## Setup

Windows PowerShell:

```powershell
cd D:\cpt
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Copy only if you do not already have a configured .env:
Copy-Item .env.example .env
```

Linux/macOS, from the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Copy only if you do not already have a configured .env:
cp .env.example .env
```

Edit `.env` with your local MySQL credentials. Never commit `.env`, place real
credentials in `.env.example`, or store a database URL in `alembic.ini`.
Prefer a dedicated application account with limited permissions; migrations
may use a separate account. The local `.env` is ignored by Git.

Activation is optional. If PowerShell blocks activation, replace `python` with
`.\.venv\Scripts\python.exe`; on Linux/macOS use `.venv/bin/python`.

## Configuration

Pydantic Settings reads the project-local `.env` as UTF-8 regardless of working
directory. Process variables override `.env`; restart after changes.

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_NAME` | `Diagnostic Platform API` | Documentation title |
| `APP_VERSION` | `1.0.0` | Documentation and health version |
| `SERVICE_NAME` | `diagnostic-platform-api` | Liveness identifier |
| `APP_ENV` | `development` | Management/pricing routes require development; active catalog GETs remain public |
| `DEBUG` | `true` | Framework debug flag; errors remain sanitized |
| `API_V1_PREFIX` | `/api/v1` | Absolute segments without trailing slash |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Intended Uvicorn bind values |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Explicit HTTP(S) origins |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `3306` | MySQL address |
| `DB_NAME` | `diagnostic_platform` | Existing database |
| `DB_USER` / `DB_PASSWORD` | unset | Required for database features |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `5` | Per-worker connection bounds |
| `DB_POOL_TIMEOUT` | `10` | Pool wait timeout in seconds |
| `DB_POOL_RECYCLE` | `1800` | Connection age limit in seconds |
| `DB_CONNECT_TIMEOUT` | `5` | Connect/read/write timeout in seconds |
| `DB_USE_NULL_POOL` | `false` | Disable retained connections |
| `DB_VERIFY_ON_STARTUP` | `false` | Run SELECT 1 at startup |

The example enables startup verification. Without database credentials, existing
liveness/documentation endpoints still work when startup verification is off.
An attempted `get_db()` dependency returns 503. Configured applications create
one engine and session factory per lifespan, connect lazily, and dispose the
engine on shutdown. Startup verification runs off the event loop and fails
startup with a sanitized error when MySQL cannot be reached. It never creates
tables or runs migrations.

Passwords use `SecretStr`; SQLAlchemy `URL.create` handles characters such as
`@`, `%`, and `/` safely. Quote `.env` values where needed. No printable plaintext
database URL is stored in configuration files.

CORS origins require a JSON array; wildcards, credentials, paths, and query
strings are rejected. Allowed methods are GET, POST, PUT, PATCH, DELETE, OPTIONS.
Authorization, Content-Type, and X-Request-ID headers are allowed. X-Request-ID
is browser-visible; credential cookies are disabled.

## Start locally

PowerShell, from `D:\cpt` with the environment activated:

```powershell
# This host inherits DEBUG=release, which is not a valid boolean:
$env:DEBUG='true'
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Linux/macOS:

```bash
export DEBUG=true
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

`uvicorn app.main:app --reload` also works. `HOST` and `PORT` in `.env` do not
automatically configure Uvicorn: pass its `--host`/`--port` flags explicitly.
Use `DEBUG=false` outside development. Stop the server with Ctrl+C.

- API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI: <http://localhost:8000/openapi.json>

Swagger/ReDoc need internet access for CDN assets; OpenAPI is served locally.

## Health and database verification

PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health | ConvertTo-Json
python -m app.db verify
```

Linux/macOS:

```bash
curl -i http://localhost:8000/api/v1/health
python -m app.db verify
```

Liveness stays public and returns HTTP 200 without querying MySQL:

```json
{"status":"healthy","service":"diagnostic-platform-api","version":"1.0.0"}
```

The verification command runs SELECT 1, inspects schema metadata, and executes
ORM SELECTs with LIMIT 0 against all ten tables. It does not read patient records,
run DDL, or change data. Success reports:

```text
MySQL connection verified; all 10 ORM tables match and are accessible.
```

Schema checks cover table/column sets, types, enum ordering, nullability, defaults
including ON UPDATE, auto-increment, primary keys, foreign keys/actions, unique
constraints, checks, unmodeled indexes, engine, and collation. MySQL integer
display widths, BOOLEAN/TINYINT(1), NUMERIC/DECIMAL, quoted numeric defaults,
timestamp formatting, and automatic FK supporting indexes are accounted for.
The Alembic version table is excluded. Differences report schema object names
without sensitive values; failures return a nonzero exit code.

## Models and sessions

`sql_scripts` is the reference for patients, laboratories, diagnostic_tests,
lab_test_prices, prescriptions, bookings, booking_tests, sample_collections,
payments, and diagnostic_reports. The application never executes this script.
Nullability follows SQL: a DEFAULT does not imply NOT NULL. Money maps to
Decimal/DECIMAL(10,2). MySQL enums, timestamp ON UPDATE, foreign keys, and unique
constraints are retained without adding ORM delete cascades.

Future synchronous endpoints can use `session: Session = Depends(get_db)` with
`app.db.session.get_db`. Each dependency creates a Session, rolls back on errors,
and always closes. Successful requests do not commit implicitly: future services
must call `session.commit()` or use `session.begin()` explicitly. Closing rolls
back uncommitted work. Never share Sessions between requests or threads; run
synchronous database work off the event loop.

## Safe Alembic baseline

Revision `0001_existing_schema` is intentionally empty: it contains no create,
alter, or drop operations. It adopts an existing matching database and cannot
bootstrap an empty database. In this workspace it was recorded after live schema
verification succeeded. Only the `alembic_version` tracking table and revision
row were added; the ten existing tables were unchanged.

For another existing deployment:

```bash
python -m app.db verify
python -m app.db baseline
python -m alembic current
python -m alembic check
```

The baseline command verifies again before stamping and refuses to overwrite a
different migration history. Alembic's environment also verifies initial adoption
and direct CLI stamps. Empty or mismatching schemas are refused before a version
table is created. Offline migrations are disabled because they cannot verify
the live schema. Repeating the matching baseline is safe. Immediately after
adoption, `alembic check` should detect no upgrade operations.

Do not run `sql_scripts`, `Base.metadata.create_all`, or an initial CREATE TABLE
migration against the existing database. Startup never invokes Alembic. Later,
generate candidate changes using `python -m alembic revision --autogenerate -m
"description"`, review all operations and the backup/migration plan, then apply
the reviewed revision explicitly with `python -m alembic upgrade head`.
Autogeneration requires human review. The baseline's downgrade does not drop
the ten existing tables.

## Errors and logging

Database errors use the existing error envelope and request ID:

```json
{
  "success": false,
  "error": {"code": "DATABASE_UNAVAILABLE", "message": "Database service is unavailable."},
  "request_id": "generated-uuid"
}
```

Integrity conflicts return 409, operational/disconnection failures 503, and other
SQLAlchemy failures 500. Driver messages, SQL, parameters, and credentials are not
exposed. Safe intentional HTTP messages below 500 and headers such as Allow and
WWW-Authenticate remain supported. Validation inputs are not echoed; CORS also
applies to failure responses. Unexpected errors remain sanitized in debug mode.

JSON logs go to stdout with request ID, method, route template, status, duration,
and database failure exception type. Startup/shutdown are logged. Exception text,
query strings, bodies, headers, dynamic path values, and unknown paths are omitted
to protect patient data. Unknown paths log as `[unmatched]`. SQL echo and Uvicorn
access logs are disabled; SQLAlchemy parameters are hidden. Do not enable SQL
logging in environments holding patient data. A streaming response cannot be
replaced after headers are sent; current endpoints do not stream.

## Automated tests

Default tests require neither MySQL nor local credentials:

```bash
python -m pytest -v
python -m pip check
```

Unit tests clear relevant environment variables and bypass `.env`. Session and
baseline tests use isolated in-memory SQLite databases; baseline tests control
schema-verification outcomes. No unit test writes to MySQL.

Enable the three read-only MySQL tests explicitly, using local `.env`:

```powershell
$env:DEBUG='true'
$env:RUN_MYSQL_TESTS='1'
python -m pytest -v
Remove-Item Env:RUN_MYSQL_TESTS
```

Linux/macOS:

```bash
DEBUG=true RUN_MYSQL_TESTS=1 python -m pytest -v
```

The verified full suite has **318 passing tests**, including all original US-001
tests and the three live MySQL tests. Default runs pass 315 and skip three. One
upstream Starlette/AnyIO BlockingPortal deprecation warning remains. Coverage
includes session cleanup, rollback and explicit commit, sanitized errors, engine
lifecycle, baseline refusal on drift, ORM contracts, connectivity, and existing
health/CORS/logging/documentation behavior. Live tests never insert or stamp.
Patient API integration tests run the HTTP, service, and repository layers with
an overridden database dependency and an isolated in-memory SQLite database.
Only private test metadata adapts auto-increment, email collation, and timestamp
defaults for SQLite. The production Patient model is unchanged. Unit tests cover
MySQL duplicate-key races and flush/refresh/commit failures. No patient test
reads or writes the development MySQL patient records.

## Patient APIs (US-003)

Patient endpoints are registered **only when APP_ENV=development** and also
check that setting per request. They return 404 and disappear from OpenAPI in
test, staging, and production environments. These APIs have no authentication;
keep the development server bound to 127.0.0.1. Set APP_ENV=production on any
deployed environment. Enabling authenticated access is a later story.

| Method and path | Behavior | Success |
| --- | --- | --- |
| POST `/api/v1/patients` | Register a patient | 201, with Location header |
| GET `/api/v1/patients/{patient_id}` | Get one patient | 200 |
| PUT `/api/v1/patients/{patient_id}` | Update supplied fields | 200 |
| GET `/api/v1/patients?page=1&page_size=20` | List patients | 200 |
| GET `/api/v1/patients/search?q=Sample&page=1&page_size=20` | Search name or phone | 200 |

All routes use the configured API prefix. Responses include the existing patient
columns, generated ID, and server timestamps. Success responses carry
Cache-Control: no-store. Missing patients return 404/PATIENT_NOT_FOUND, duplicate
emails 409/DUPLICATE_EMAIL, and invalid requests 422/VALIDATION_ERROR in the common
error envelope. Database failures use the existing sanitized 409/500/503 handling.

Registration requires full_name and phone. Email, date_of_birth, gender, address,
district, and pincode are optional and nullable. Email is validated, trimmed,
stored lowercase, and protected by the existing MySQL unique constraint even
when concurrent writes bypass the preliminary duplicate check. Multiple patients
can omit email. Phone allows 7–15 digits with an optional leading plus, spaces,
hyphens, and parentheses, within the existing 20-character column. Date of birth
must be on or before today and within MySQL DATE's supported year range.
Names and optional strings are trimmed and bounded by column sizes; address is
limited to 16,000 characters to fit utf8mb4 TEXT. Unknown fields are rejected.

PUT updates only supplied fields and preserves omitted fields. Explicit null
clears nullable columns; full_name and phone cannot be null or blank. Empty
updates are rejected. IDs and timestamps are read-only. Reusing the same patient's
email is allowed; using another patient's email returns 409 without saving changes.
The service explicitly commits successful writes and rolls back failed writes.

Listing/search return an envelope with items, total, page, page_size, and pages.
Page numbers start at 1; page_size defaults to 20 and is limited to 100. Page is
bounded to 1,000,000. Results are ordered by patient_id ascending; out-of-range
pages return empty items. Search requires a nonblank q of up to 150 characters,
matches substrings in name or phone as stored, and uses the database collation.
SQL wildcard characters are escaped as literal input and all values are bound
through SQLAlchemy. Search text and patient data are excluded from logs.

### Manual local testing

Install updated requirements using the explicit virtual-environment interpreter
to avoid selecting the system Python:

```powershell
cd D:\cpt
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEBUG='true'
$env:APP_ENV='development'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1
```

Open <http://localhost:8000/docs>; the Patients tag documents each operation,
request/response schema, and error response. The following manual calls create
and update a synthetic record in your configured local database; automated tests
instead use their isolated database.

```powershell
$body = @{
    full_name = 'Sample Patient'
    phone = '9876543210'
    email = 'local.patient@example.com'
    date_of_birth = '1995-04-12'
} | ConvertTo-Json
$patient = Invoke-RestMethod -Method Post `
    -Uri http://localhost:8000/api/v1/patients `
    -ContentType application/json -Body $body
Invoke-RestMethod "http://localhost:8000/api/v1/patients/$($patient.patient_id)"
Invoke-RestMethod -Method Put `
    -Uri "http://localhost:8000/api/v1/patients/$($patient.patient_id)" `
    -ContentType application/json -Body '{"district":"Sample district"}'
Invoke-RestMethod 'http://localhost:8000/api/v1/patients?page=1&page_size=10'
Invoke-RestMethod 'http://localhost:8000/api/v1/patients/search?q=Sample'
```

Linux/macOS registration example:

```bash
curl -X POST http://localhost:8000/api/v1/patients \
  -H 'Content-Type: application/json' \
  -d '{"full_name":"Sample Patient","phone":"9876543210","email":"local.patient@example.com"}'
```

Run the patient tests without accessing local MySQL records:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_patients.py tests/test_patient_service.py -v
```

No Patient model, table, or migration changes were required for US-003. Alembic's
existing baseline was checked before implementation; no migration was applied.

## Laboratory APIs (US-004)

Laboratory management is administrative functionality. Authentication and
administrator authorization are prerequisites for production exposure. Because
neither exists yet, all six endpoints are registered only with
APP_ENV=development, use the shared per-request development guard, and are absent
from routes/OpenAPI in test, staging, and production. This local restriction is
not authentication. Bind to 127.0.0.1 and use APP_ENV=production when deploying.
No administrator credentials or alternate database engine are introduced.
The offered-tests/cost endpoint added in US-005 follows the same restriction.

| Method and path | Behavior | Success |
| --- | --- | --- |
| POST `/api/v1/laboratories` | Register with PENDING status | 201, Location header |
| GET `/api/v1/laboratories` | Paginated laboratory listing | 200 |
| GET `/api/v1/laboratories/search?q=Sample` | Search name, district, or pincode | 200 |
| GET `/api/v1/laboratories/{lab_id}` | Retrieve a laboratory | 200 |
| PUT `/api/v1/laboratories/{lab_id}` | Update supplied detail fields | 200 |
| PATCH `/api/v1/laboratories/{lab_id}/status` | Change status separately | 200 |

The configured API prefix applies to all paths. Responses contain the existing
table fields, timestamps, and a read-only eligible_for_booking flag, which is true
only for ACTIVE laboratories. This flag describes status eligibility; no pricing,
booking assignment, or other booking logic is implemented. Results use
Cache-Control: no-store and the existing request IDs and error envelope.

Only lab_name is required for registration. Optional contact_person, phone,
email, address, district, pincode, and accreditation_number follow the table's
nullability and length limits. Name must be nonblank and at most 200 characters;
contact_person is limited to 150, district/accreditation_number to 100, and address
to 16,000 characters for utf8mb4 TEXT. Phone uses the shared patient validation:
7–15 digits, optional leading plus/spaces/hyphens/parentheses, at most 20 total
characters. Email uses the existing validator and is trimmed and lowercased.
Laboratory email is not unique in the existing schema; this story adds no new
uniqueness rule. Pincode accepts six ASCII digits beginning with 1–9 (for example,
560001); it remains a string to preserve its format. Optional fields can be null.

Registration never accepts a client-supplied status. New laboratories start as
PENDING. PUT changes only supplied fields, preserves omitted fields, and permits
explicit null for optional columns. Empty updates and null/blank lab_name are
rejected. IDs, timestamps, eligibility, and status cannot be written through
registration/detail schemas. Status changes require the separate PATCH operation.

| Current status | Allowed new status |
| --- | --- |
| PENDING | ACTIVE or INACTIVE |
| ACTIVE | INACTIVE |
| INACTIVE | ACTIVE |

Repeating the current status is idempotent and returns 200. Returning ACTIVE or
INACTIVE to PENDING returns 409/INVALID_LABORATORY_STATUS_TRANSITION. Unknown,
lowercase, or null status inputs return 422. The existing table permits legacy
null statuses; those read as null and are ineligible, and transitions are rejected
until the legacy data is explicitly reconciled. No existing records are repaired
automatically.

Missing laboratories return 404/LABORATORY_NOT_FOUND. IDs must be positive signed
BIGINT values; invalid IDs or input return 422. Database errors retain the existing
sanitized 409/500/503 handling. Detail and status updates lock the selected row on
MySQL before checking/changing it. Successful writes flush, refresh server values,
and commit; failed writes roll back through the existing session dependency and
service handling. No SQL, contact details, request bodies, or search terms are
logged or included in database-error messages.

Listing/search use page=1 and page_size=20 by default; page_size is capped at 100
and page at 1,000,000. The response envelope has items, total, page, page_size, and
pages, ordered by lab_id ascending. Search requires a nonblank q of at most 200
characters and matches any of name, district, or pincode as substrings. Queries
are parameterized, SQL wildcards are escaped as literals, and comparisons follow
database collation. Empty matches and out-of-range pages return empty items.

### Local laboratory testing

Use the existing environment and database configuration. Start with the explicit
virtual-environment interpreter, then open <http://localhost:8000/docs> and expand
the Laboratories tag:

```powershell
cd D:\cpt
$env:DEBUG='true'
$env:APP_ENV='development'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1
```

These manual requests intentionally create and modify a synthetic record in the
configured local database. Automated laboratory tests use isolated SQLite only:

```powershell
$body = @{
    lab_name = 'Sample Laboratory'
    email = 'sample.lab@example.com'
    phone = '9876543210'
    district = 'Bengaluru'
    pincode = '560001'
} | ConvertTo-Json
$lab = Invoke-RestMethod -Method Post `
    -Uri http://localhost:8000/api/v1/laboratories `
    -ContentType application/json -Body $body
Invoke-RestMethod "http://localhost:8000/api/v1/laboratories/$($lab.lab_id)"
Invoke-RestMethod -Method Put `
    -Uri "http://localhost:8000/api/v1/laboratories/$($lab.lab_id)" `
    -ContentType application/json -Body '{"contact_person":"Sample Contact"}'
Invoke-RestMethod 'http://localhost:8000/api/v1/laboratories?page=1&page_size=10'
Invoke-RestMethod 'http://localhost:8000/api/v1/laboratories/search?q=560001'
Invoke-RestMethod -Method Patch `
    -Uri "http://localhost:8000/api/v1/laboratories/$($lab.lab_id)/status" `
    -ContentType application/json -Body '{"status":"ACTIVE"}'
Invoke-RestMethod -Method Patch `
    -Uri "http://localhost:8000/api/v1/laboratories/$($lab.lab_id)/status" `
    -ContentType application/json -Body '{"status":"INACTIVE"}'
```

Linux/macOS registration example:

```bash
curl -X POST http://localhost:8000/api/v1/laboratories \
  -H 'Content-Type: application/json' \
  -d '{"lab_name":"Sample Laboratory","district":"Bengaluru","pincode":"560001"}'
```

Run only the new tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_laboratories.py tests/test_laboratory_service.py -v
```

Tests cover registration defaults, validation, missing/invalid IDs, immutable IDs,
updates, pagination, all search fields, literal search input, the status matrix,
database failures/rollbacks, contact-log privacy, development guards, Swagger, and
patient API compatibility. Test-only cloned tables adapt auto-increment, enum,
and timestamp definitions for SQLite. SQLite does not simulate MySQL row locking;
the service unit tests verify that updates request a locked row. The optional
existing MySQL tests remain read-only and verify live schema/connectivity. No
development or production data is modified by automated tests.

US-004 reuses the existing Laboratory ORM model and table. The live schema and
Alembic baseline were checked; no model changes, migrations, or new dependencies
were needed. No authentication, pricing, payments, prescriptions, or frontend
features were added.

## Diagnostic catalog and common pricing (US-005)

Every diagnostic test has one platform_price, independent of its performing lab.
LabTestPrice.lab_price is the negotiated cost, not a patient selling price. Public
catalog responses contain only test details and the common price; costs, spreads,
and margins are returned only by the development-restricted pricing APIs.

The following GET operations are available in every environment and show only
active tests with a positive platform price. A hidden/inactive test returns 404.

| Method and path | Behavior |
| --- | --- |
| GET `/api/v1/diagnostic-tests` | Paginated active catalog |
| GET `/api/v1/diagnostic-tests/search?q=CBC` | Search name, code, or category |
| GET `/api/v1/diagnostic-tests/{test_id}` | Public test details/common price |

These operations require APP_ENV=development until real administrator
authentication/authorization is implemented. They are omitted from deployed
OpenAPI and also check the shared development guard on each request:

| Method and path | Behavior |
| --- | --- |
| POST `/api/v1/diagnostic-tests` | Create an active test (201) |
| PUT `/api/v1/diagnostic-tests/{test_id}` | Update supplied detail fields |
| PATCH `/api/v1/diagnostic-tests/{test_id}/status` | Activate/deactivate |
| PATCH `/api/v1/diagnostic-tests/{test_id}/price` | Change common selling price |
| POST `/api/v1/laboratory-test-prices` | Create unique lab/test mapping (201) |
| GET `/api/v1/laboratory-test-prices` | List private negotiated costs |
| GET `/api/v1/laboratories/{lab_id}/tests` | Tests/costs offered by a lab (private) |
| PUT `/api/v1/laboratory-test-prices/{lab_test_id}` | Change negotiated cost |
| PATCH `/api/v1/laboratory-test-prices/{lab_test_id}/availability` | Change availability |
| GET `/api/v1/diagnostic-tests/{test_id}/pricing-comparison` | Private margin comparison |

Public read paths still exist in production, so attempts to POST/PUT those paths
receive 405; private-only pricing paths receive 404. No negotiated costs appear
in production response schemas. In development only, add include_inactive=true
to catalog list/search/detail queries to inspect inactive or legacy invalid-price
tests. Outside development that option is rejected with 404. It never adds costs
to the public test response shape.

All lists, search, offered tests, and comparisons support page=1/page_size=20 by
default, page_size at most 100 and page at most 1,000,000. Lists use items, total,
page, page_size, pages and stable ID ordering. Search requires a nonblank q (up to
200 characters), escapes wildcard characters literally, and uses bound SQLAlchemy
queries and database collation. Negotiated-cost lists also accept lab_id/test_id
filters. Comparison includes mappings for pending/inactive labs and unavailable
tests so administrators can review them, with eligibility explicitly indicated.

### Validation and pricing rules

- Test creation requires test_name, test_code, and platform_price. Optional fields
  are category, description, and sample_type. Name is limited to 200 characters,
  code to 50, category/sample_type to 100, description to 16,000. Codes accept
  letters/digits/underscores/hyphens, begin with a letter or digit, are trimmed and
  uppercased, and remain unique through the existing database constraint.
- New tests are active. Status and ID cannot be supplied at creation. PUT changes
  only supplied details; null clears optional detail fields but cannot clear name
  or code. Price/status changes use their dedicated PATCH operations.
- Money inputs are decimal strings (recommended) or integers. Fractional JSON
  numbers and booleans are rejected to prevent conversion through binary floats.
  Prices must be finite, greater than zero, no more than 99,999,999.99, and have at
  most two meaningful decimal places. API money/percentage outputs are strings.
  This schema has no currency column; selling price and cost must use the same
  business currency. No currency conversion is performed.
- Each lab/test pair is unique. Both referenced records must exist. Missing
  records return 404; invalid IDs return 422; duplicate codes/mappings return 409
  with DUPLICATE_TEST_CODE or DUPLICATE_LAB_TEST_MAPPING, including concurrent
  duplicate writes. Other database errors use the existing sanitized handlers.
- A mapping may be negotiated before a lab is active, but its effective
  eligible_for_booking flag is true only when the lab is ACTIVE, the test is
  active, the mapping is available, and both prices are positive. Availability
  defaults to true unless explicitly supplied. Null legacy flags are ineligible.
  Activating a test or mapping never activates a lab automatically.
- Mapping lab_id/test_id and all generated IDs/timestamps are immutable. Mapping
  PUT accepts only lab_price; availability changes use PATCH. Boolean status and
  availability inputs must be literal JSON true or false, not strings or integers.
- Common-price updates write only diagnostic_tests.platform_price. They do not
  update bookings.total_amount, booking_tests.price_at_booking, or lab costs.
  No booking creation or assignment is implemented by this story.

Calculations use Decimal with sufficient intermediate precision and ROUND_HALF_UP
to two decimal places for displayed amounts and percentages:

```text
gross_spread = platform_price - lab_price
gross_margin_percentage = gross_spread / platform_price * 100
markup_percentage = gross_spread / lab_price * 100
```

For a selling price of 500.00 and cost of 300.00, the spread is 200.00, gross margin
40.00%, and markup 66.67%. A cost of 600.00 returns -100.00, -20.00%, and -16.67%,
with negative_margin=true and requires_review=true. Negative margins remain
negative; the system does not take an absolute value or label them as profit.
Legacy zero/negative stored prices cause comparison to return
409/INVALID_STORED_PRICE rather than divide by zero. Administrators must reconcile
those prices explicitly. Negative-margin flags request review but do not implement
a new booking-approval workflow.

### Payloads for local testing

Start using the existing virtual environment and MySQL configuration:

```powershell
cd D:\cpt
$env:DEBUG='true'
$env:APP_ENV='development'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1
```

Open <http://localhost:8000/docs>. The Diagnostic Tests, Catalog Administration,
and Laboratory Pricing tags document all operations. The following manual
requests create/update records in the configured local database; automated tests
use their isolated database. Replace IDs with the values returned on creation.

Create a test with POST `/api/v1/diagnostic-tests`:

```json
{
  "test_name": "Complete Blood Count",
  "test_code": "CBC",
  "category": "Hematology",
  "description": "Synthetic local catalog example",
  "sample_type": "Blood",
  "platform_price": "500.00"
}
```

Update details with PUT `/api/v1/diagnostic-tests/1`:

```json
{"test_name":"Complete Blood Count Panel","sample_type":"Blood"}
```

Activate/deactivate using PATCH `/api/v1/diagnostic-tests/1/status`:

```json
{"is_active":false}
```

Send `{"is_active":true}` to reactivate. Change the common price with PATCH
`/api/v1/diagnostic-tests/1/price`:

```json
{"platform_price":"550.00"}
```

Map an existing laboratory to an existing test using POST
`/api/v1/laboratory-test-prices`:

```json
{"lab_id":1,"test_id":1,"lab_price":"300.00","is_available":true}
```

Update negotiated cost with PUT `/api/v1/laboratory-test-prices/1`:

```json
{"lab_price":"325.00"}
```

Disable availability with PATCH `/api/v1/laboratory-test-prices/1/availability`:

```json
{"is_available":false}
```

Send `{"is_available":true}` to restore it. GET requests have no body:

```text
/api/v1/diagnostic-tests?page=1&page_size=10
/api/v1/diagnostic-tests/search?q=CBC
/api/v1/diagnostic-tests/1
/api/v1/diagnostic-tests/1?include_inactive=true
/api/v1/laboratory-test-prices?lab_id=1&page_size=10
/api/v1/laboratories/1/tests
/api/v1/diagnostic-tests/1/pricing-comparison?page=1&page_size=10
```

Negotiated costs/comparisons use Cache-Control: no-store. The shared logger omits
request bodies, price values, credentials, and search text. Existing patient and
laboratory APIs remain available under their original development guards.

### Verification and scope

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_catalog.py tests/test_catalog_service.py -v
.\.venv\Scripts\python.exe -m pytest -v
$env:DEBUG='true'
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m app.db verify
```

The new tests run HTTP/service/repository integration against private SQLite
tables with foreign keys enabled, plus unit tests for Decimal calculations,
MySQL duplicate-key failures, eligibility combinations, and transaction failures.
Historical booking preservation is tested using synthetic records only. Public
cost isolation and production route/schema restrictions are tested explicitly.
The optional existing MySQL tests remain read-only. No real patient, booking,
laboratory, or catalog data is modified by automated tests.

US-005 reuses the existing DiagnosticTest/LabTestPrice models and database
infrastructure. Live schema verification and Alembic checks passed; no migration,
table modification, or new dependency was needed. No bookings, payments,
prescriptions, collections, or frontend functionality was implemented.

## Troubleshooting

- **MySQL unreachable:** check the Windows MySQL80 service, host, port, firewall,
  credentials, and account host permissions. Use `python -m app.db verify`.
- **Authentication error:** install the pinned `PyMySQL[rsa]` requirements for
  MySQL 8 support. Check credentials locally without logging them.
- **DEBUG validation error:** process values such as DEBUG=release override
  `.env`; set `$env:DEBUG='true'` or `export DEBUG=true`.
- **Schema mismatch:** compare the reported objects with SHOW CREATE TABLE and
  `sql_scripts`. Reconcile intended mappings before baselining; never alter
  existing data automatically to make a comparison pass.
- **Missing credentials:** set DB_USER/DB_PASSWORD before database commands.
  The health endpoint alone does not test connectivity.
- **Module not found:** run from `cpt/` using `.venv`'s Python and install the
  pinned requirements. On Linux install the Python 3.11 venv package if needed.
- **Dependency download blocked:** check proxy/network permissions and PyPI access.
- **Port occupied:** stop the other server or choose `--port 8001`.
- **CORS failure:** match the frontend scheme, host, and port exactly; localhost
  and 127.0.0.1 differ. Restart after edits.
- **Docs unavailable offline:** Swagger/ReDoc require CDN assets; OpenAPI is local.

## Future AWS Lambda deployment

The app remains stateless and exposes standard ASGI. A later story can add Mangum
and API Gateway without rewriting routes or models. Supply secrets through
deployment configuration or a secret manager, provide MySQL network access,
review adapter lifespan behavior, and bound connections per execution environment.
`DB_USE_NULL_POOL=true` disables retained connections when appropriate; a future
deployment may use a small pool and RDS Proxy instead. Never retain a request
Session across invocations. Review startup checks and timeouts for cold starts.
Stdout logs support CloudWatch ingestion. Patient/laboratory routes must remain disabled
outside local development until authentication and authorization exist.
No AWS deployment is introduced in these stories.
