# Initial Secure Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a security-first student pre-registration flow and authenticated staff lookup using fake data.

**Architecture:** FastAPI serves Jinja2 pages. Pydantic validates untrusted form data, focused services own registration and authentication decisions, and SQLAlchemy persists records in SQLite behind dependency-injected sessions. Public confirmation exposes only a cryptographically random code; sensitive details remain behind a signed staff session.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, SQLAlchemy 2, Pydantic 2, SQLite, Argon2, pytest, Ruff, Uvicorn

**Spec:** `docs/superpowers/specs/2026-09-29-hsk-registration-design.md`

## Global Constraints

- Use fake data only; never commit real identity information or credentials.
- Do not store passport images, add OCR, add AI features, or add React.
- Student-created registrations always begin as `PENDING`.
- Public pages never reveal passport, birth-date, or phone data after submission.
- Configuration and secrets come from environment variables; production mode rejects insecure defaults.
- SQLite remains a prototype datastore and is not approved for institutional production.
- Every task ends with passing focused tests and a small conventional commit.

## Review Focus

- Whitespace-only names and identifiers must fail server-side validation.
- Unexpected HSK values, including case variants and `HSK99`, must fail validation.
- Public success responses must not contain submitted passport or phone values.
- Authentication errors must not reveal whether a staff username exists.
- Malformed, lowercase, or missing registration codes must return a generic not-found response without leaking records.

---

### Task 1: Reproducible application foundation

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/main.py`
- Test: `tests/test_config.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Produces: `Settings.from_env(environ: Mapping[str, str]) -> Settings`
- Produces: `create_app(settings: Settings | None = None) -> FastAPI`
- Produces: `GET /health` returning `{"status": "ok"}`

- [ ] **Step 1: Write failing configuration and health tests**

Test development defaults, production rejection of a missing `SESSION_SECRET`, and the exact health response.

- [ ] **Step 2: Run focused tests and verify import/test failures**

Run: `.venv/bin/pytest tests/test_config.py tests/test_health.py -v`

- [ ] **Step 3: Implement minimal settings and app factory**

Keep environment parsing deterministic and inject settings into `app.state`.

- [ ] **Step 4: Add pinned runtime/dev dependencies and environment example**

Include FastAPI, Uvicorn, SQLAlchemy, Jinja2, multipart parsing, Argon2, pytest, HTTPX, Ruff, and coverage tooling with exact installed versions.

- [ ] **Step 5: Verify tests and lint pass**

Run: `.venv/bin/pytest tests/test_config.py tests/test_health.py -v && .venv/bin/ruff check .`

- [ ] **Step 6: Commit**

Commit: `chore: establish secure application foundation`

### Task 2: Registration domain and persistence

**Files:**
- Create: `app/database.py`
- Create: `app/models.py`
- Create: `app/schemas.py`
- Create: `app/services/__init__.py`
- Create: `app/services/registration_service.py`
- Test: `tests/conftest.py`
- Test: `tests/test_registration_service.py`

**Interfaces:**
- Produces: `RegistrationStatus` and `HSKLevel` string enums
- Produces: `RegistrationCreate` validated input model
- Produces: `create_registration(db: Session, data: RegistrationCreate) -> Registration`
- Produces: `find_registration_by_code(db: Session, code: str) -> Registration | None`
- Produces: `get_db(request: Request) -> Iterator[Session]`

- [ ] **Step 1: Write failing model, validation, and service tests**

Cover valid persistence, `PENDING` default, code shape/uniqueness, whitespace-only input, invalid HSK values, missing records, and SQLite constraints.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_registration_service.py -v`

- [ ] **Step 3: Implement database lifecycle, enums, model, schema, and service**

Use SQLAlchemy 2 typed mappings, a status check constraint, normalized public-code lookup, and `secrets.choice` over an unambiguous alphabet.

- [ ] **Step 4: Verify focused and complete tests**

Run: `.venv/bin/pytest -v && .venv/bin/ruff check .`

- [ ] **Step 5: Commit**

Commit: `feat: add validated registration persistence`

### Task 3: Public student registration flow

**Files:**
- Create: `app/routes/__init__.py`
- Create: `app/routes/student.py`
- Create: `app/templates/base.html`
- Create: `app/templates/registration_form.html`
- Create: `app/templates/registration_success.html`
- Create: `app/static/styles.css`
- Modify: `app/main.py`
- Test: `tests/test_student_routes.py`

**Interfaces:**
- Produces: `GET /` student form
- Produces: `POST /registrations` validated submission endpoint
- Produces: `GET /registration/success/{code}` code-only confirmation

- [ ] **Step 1: Write failing route tests**

Cover form rendering, valid redirect/persistence, invalid form feedback, unsupported HSK level, code-only success output, and unknown-code behavior.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_student_routes.py -v`

- [ ] **Step 3: Implement public routes and templates**

On validation failure return status 422 with safe field messages; never echo passport or phone values into error or success pages.

- [ ] **Step 4: Add baseline response-security middleware**

Set content-type sniffing, framing, referrer, permissions, and content-security headers without breaking local static assets.

- [ ] **Step 5: Verify focused and complete tests**

Run: `.venv/bin/pytest -v && .venv/bin/ruff check .`

- [ ] **Step 6: Commit**

Commit: `feat: add public pre-registration flow`

### Task 4: Staff authentication

**Files:**
- Create: `app/security.py`
- Create: `app/services/auth_service.py`
- Create: `app/routes/staff.py`
- Create: `app/templates/staff_login.html`
- Create: `scripts/create_staff_user.py`
- Modify: `app/models.py`
- Modify: `app/main.py`
- Test: `tests/test_auth_service.py`
- Test: `tests/test_staff_auth.py`

**Interfaces:**
- Produces: `hash_password(password: str) -> str`
- Produces: `verify_password(password: str, password_hash: str) -> bool`
- Produces: `authenticate_staff(db: Session, username: str, password: str) -> StaffUser | None`
- Produces: signed-session login at `GET|POST /staff/login` and logout at `POST /staff/logout`
- Produces: `require_staff(request: Request) -> StaffUser`

- [ ] **Step 1: Write failing password, user, session, and generic-error tests**

Cover Argon2 hashing, correct/incorrect verification, inactive users, unknown/equivalent login failures, protected-route redirects, cookie flags, and logout.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_auth_service.py tests/test_staff_auth.py -v`

- [ ] **Step 3: Implement staff model, password service, signed sessions, and bootstrap script**

Use a generic login error and avoid logging supplied credentials. Cookie policy is `HttpOnly`, `SameSite=Lax`, and `Secure` in production.

- [ ] **Step 4: Verify focused and complete tests**

Run: `.venv/bin/pytest -v && .venv/bin/ruff check .`

- [ ] **Step 5: Commit**

Commit: `feat: add secure staff authentication`

### Task 5: Protected staff lookup and operational documentation

**Files:**
- Modify: `app/routes/staff.py`
- Create: `app/templates/staff_search.html`
- Create: `app/templates/staff_registration.html`
- Create: `tests/test_staff_lookup.py`
- Create: `README.md`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `GET /staff` authenticated search form
- Produces: `GET /staff/registrations/{code}` authenticated, read-only detail view

- [ ] **Step 1: Write failing protected-lookup tests**

Cover authentication enforcement, valid lookup, malformed/lowercase/unknown code behavior, and display of all required staff-only fields.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_staff_lookup.py -v`

- [ ] **Step 3: Implement search and detail routes/templates**

Normalize valid lowercase codes but return the same generic 404 view for malformed and unknown codes.

- [ ] **Step 4: Document secure local setup and production gates**

Document fake-data-only use, staff bootstrap, configuration, test/run commands, sensitive-data boundaries, SQLite limitations, and the prerequisites for real deployment.

- [ ] **Step 5: Add CI and run the full verification suite**

Run: `.venv/bin/ruff check . && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=85`

- [ ] **Step 6: Commit**

Commit: `feat: add protected staff registration lookup`

### Task 6: Final security and delivery verification

**Files:**
- Modify only files required by discovered verification failures

**Interfaces:**
- Consumes all earlier task interfaces; produces a reviewed, runnable first milestone.

- [ ] **Step 1: Audit repository contents and tracked files**

Confirm no database, `.env`, credentials, generated documents, private keys, or personal data is tracked.

- [ ] **Step 2: Run quality, security, and behavior checks**

Run lint, full tests with coverage, dependency audit, package build/install smoke test, and an application startup smoke test.

- [ ] **Step 3: Inspect HTTP behavior manually**

Confirm public confirmation is code-only, staff data requires authentication, cookies/headers match the design, and logs do not contain submitted sensitive values.

- [ ] **Step 4: Commit only if verification required fixes**

Commit: `fix: harden initial registration workflow`

- [ ] **Step 5: Push the feature branch and prepare integration**

Push a non-`main` branch and create a pull request with verification evidence.
