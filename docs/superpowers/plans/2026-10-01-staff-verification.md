# Staff Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure staff corrections, auditable verification/rejection, CSRF protection, and schema migrations.

**Architecture:** Alembic owns persistent schema changes. A focused verification service performs version-checked mutations and creates redacted audit events in the same transaction. Routes authenticate and authorize staff, validate CSRF and form input, then delegate all business rules to the service.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2, Alembic 1.20, Pydantic 2, Jinja2, SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-10-01-staff-verification-design.md`

## Global Constraints

- Use fake data only; never commit real identity information or credentials.
- Only active `REGISTRATION_STAFF` users may mutate registrations.
- Only `PENDING` registrations may be edited, verified, or rejected.
- The only transitions are `PENDING -> VERIFIED` and `PENDING -> REJECTED`.
- Every accepted mutation and its audit row commit atomically.
- Audit rows contain changed field names, never old or new sensitive values.
- Every state-changing staff POST requires a session-bound CSRF token.
- Every feature is committed and pushed directly to `main` after full verification.

## Review Focus

- A stale browser form must never overwrite a newer correction or transition.
- An unchanged edit must not increment version or create an audit event.
- Wrong-role and inactive accounts must receive no registration details from mutation endpoints.
- Missing, malformed, or cross-session CSRF tokens must fail before any database write.
- Audit insertion failure must roll back the registration mutation completely.

---

### Task 1: Alembic migrations and versioned audit schema

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial_schema.py`
- Create: `alembic/versions/0002_staff_verification.py`
- Modify: `app/models.py`
- Modify: `app/main.py`
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Test: `tests/test_migrations.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Produces: `Registration.version: int`
- Produces: `AuditAction` enum and `AuditLog` SQLAlchemy model
- Produces: Alembic upgrade from an empty database to `head`
- Produces: production startup that does not call `create_all`

- [ ] **Step 1: Write failing migration and production-startup tests**

Test blank-database upgrade, expected tables/columns/constraints, current Alembic revision, and absence of schema creation in production.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_migrations.py tests/test_health.py -v`

- [ ] **Step 3: Add Alembic configuration and two explicit revisions**

Revision `0001` creates the existing schema. Revision `0002` adds registration versioning and `audit_logs`; both support SQLite and PostgreSQL-compatible SQLAlchemy types.

Enable SQLite foreign-key enforcement on every connection so test and prototype behavior matches declared relationships.

- [ ] **Step 4: Update ORM models and startup schema policy**

Development/test may call `create_all`; production never creates or alters tables during application import or startup.

- [ ] **Step 5: Verify full suite, lint, migration upgrade, and dependency audit**

Run: `.venv/bin/ruff check . && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=85 && .venv/bin/pip-audit -r requirements.txt`

- [ ] **Step 6: Commit and push**

Commit: `feat: add database migrations and audit schema`

### Task 2: Session CSRF and mutation authorization

**Files:**
- Create: `app/csrf.py`
- Modify: `app/routes/staff.py`
- Modify: `app/templates/staff_login.html`
- Modify: `app/templates/staff_search.html`
- Modify: `app/templates/staff_registration.html`
- Test: `tests/test_csrf.py`
- Test: `tests/test_staff_auth.py`

**Interfaces:**
- Produces: `get_csrf_token(request: Request) -> str`
- Produces: `validate_csrf_token(request: Request, submitted_token: str) -> None`
- Produces: `require_registration_staff(request: Request) -> StaffUser`

- [ ] **Step 1: Write failing CSRF and role-authorization tests**

Cover stable per-session tokens, cross-session rejection, missing/invalid login and logout tokens, rotation after login, wrong-role/inactive denial, and no mutation on failure.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_csrf.py tests/test_staff_auth.py -v`

- [ ] **Step 3: Implement CSRF helpers and role-aware staff dependency**

Generate tokens with `secrets.token_urlsafe(32)`, compare with `secrets.compare_digest`, and return generic `403` responses.

- [ ] **Step 4: Add tokens to every existing staff POST form**

Login establishes a pre-authentication session token; successful authentication clears the session and rotates it.

- [ ] **Step 5: Verify full suite and lint**

Run: `.venv/bin/ruff check . && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=85`

- [ ] **Step 6: Commit and push**

Commit: `feat: protect staff actions with CSRF tokens`

### Task 3: Transactional correction and audit service

**Files:**
- Create: `app/services/verification_service.py`
- Modify: `app/schemas.py`
- Test: `tests/test_verification_service.py`

**Interfaces:**
- Produces: `RegistrationConflictError`, `RegistrationStateError`, and `RegistrationNotFoundError`
- Produces: `update_pending_registration(db, registration_id, staff_user_id, expected_version, data) -> Registration`

- [ ] **Step 1: Write failing correction-service tests**

Cover allowed-field edits, redacted `changed_fields`, unchanged submissions, terminal records, stale versions, missing records, wrong staff IDs, and audit-failure rollback.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_verification_service.py -v`

- [ ] **Step 3: Implement validated optimistic update and audit creation**

Use one transaction and a conditional update matching `id`, `PENDING`, and `expected_version`; increment version only for a real change.

- [ ] **Step 4: Verify full suite and lint**

Run: `.venv/bin/ruff check . && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=85`

- [ ] **Step 5: Commit and push**

Commit: `feat: record audited staff corrections`

### Task 4: Edit interface and conflict handling

**Files:**
- Modify: `app/routes/staff.py`
- Create: `app/templates/staff_registration_edit.html`
- Modify: `app/templates/staff_registration.html`
- Test: `tests/test_staff_edit.py`

**Interfaces:**
- Produces: `GET /staff/registrations/{code}/edit`
- Produces: `POST /staff/registrations/{code}/edit`

- [ ] **Step 1: Write failing edit-route tests**

Cover authentication, role, CSRF, pending-only form access, safe validation feedback, successful PRG redirect, unchanged submissions, stale `409`, and terminal `409`.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_staff_edit.py -v`

- [ ] **Step 3: Implement edit routes and template**

Keep sensitive values inside authenticated, `no-store` responses; map service exceptions to generic `404`, `403`, or `409` pages without leaking a record.

- [ ] **Step 4: Verify full suite and lint**

Run: `.venv/bin/ruff check . && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=85`

- [ ] **Step 5: Commit and push**

Commit: `feat: let staff correct pending registrations`

### Task 5: Verified and rejected state transitions

**Files:**
- Modify: `app/services/verification_service.py`
- Modify: `app/routes/staff.py`
- Modify: `app/templates/staff_registration.html`
- Test: `tests/test_verification_service.py`
- Test: `tests/test_staff_transitions.py`

**Interfaces:**
- Produces: `verify_registration(db, registration_id, staff_user_id, expected_version) -> Registration`
- Produces: `reject_registration(db, registration_id, staff_user_id, expected_version) -> Registration`
- Produces: `POST /staff/registrations/{code}/verify`
- Produces: `POST /staff/registrations/{code}/reject`

- [ ] **Step 1: Write failing transition service and route tests**

Cover correct status/timestamps/verifier, one redacted audit row, CSRF, authorization, stale conflicts, repeated transitions, rejection fields, and rollback on audit failure.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `.venv/bin/pytest tests/test_verification_service.py tests/test_staff_transitions.py -v`

- [ ] **Step 3: Implement atomic transition services**

Use conditional updates matching `PENDING` and version; create exactly one audit event in the same transaction.

- [ ] **Step 4: Implement routes and terminal-state UI**

Pending records show edit/verify/reject forms with CSRF and version fields; terminal records are read-only and show audit metadata without sensitive historical values.

- [ ] **Step 5: Verify full suite and lint**

Run: `.venv/bin/ruff check . && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=85`

- [ ] **Step 6: Commit and push**

Commit: `feat: add auditable verification decisions`

### Task 6: Documentation and final security verification

**Files:**
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`
- Modify only other files required by verified failures

**Interfaces:**
- Consumes all prior interfaces and produces the completed staff-verification milestone.

- [ ] **Step 1: Update operator and workflow documentation**

Document Alembic commands, existing fake-database reset/stamp options, CSRF behavior, terminal states, audit redaction, and production migration rules.

- [ ] **Step 2: Run repository, migration, package, security, and live HTTP checks**

Run lint, 85%+ coverage, dependency audit, clean migration upgrade, package installation, startup smoke test, authenticated edit/verify/reject checks, and secret/tracked-data scans.

- [ ] **Step 3: Complete whole-branch review and one TDD fix pass**

Review against the spec and Review Focus list; fix every Critical or Important finding with RED→GREEN evidence.

- [ ] **Step 4: Commit and push verified fixes or documentation**

Commit: `docs: document staff verification operations` or a specific human-readable fix message.

- [ ] **Step 5: Confirm final `main` and GitHub CI**

Require a clean `main`, only the remote `main` branch, and a successful CI run for the final commit.
