# HSK Pre-Registration and Verification System

A security-first prototype that moves repetitive registration typing away from the institute desk. Students submit their information before arrival; authenticated staff retrieve it and compare it with the physical passport.

> **Prototype safety rule:** use fake data only. This repository is not approved to hold real passport numbers, birth dates, or phone numbers.

## What this milestone includes

- Public student pre-registration form
- Server-side Pydantic validation and database constraints
- Cryptographically random public registration codes
- Code-only public confirmation page
- Argon2 password hashing and signed staff sessions
- Session-bound CSRF protection for every staff POST request
- Role-restricted staff lookup and correction workflow
- Optimistic locking that prevents stale forms from overwriting newer work
- Audited `PENDING` to `VERIFIED` or `REJECTED` decisions
- SQLite persistence for local demonstration
- Explicit Alembic database migrations
- Automated tests, linting, coverage, and dependency auditing

DOCX generation, payments, passport images, OCR, and AI are intentionally outside this milestone.

## Local setup

Python 3.12–3.14 is supported.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env
```

The application reads environment variables directly. Export them in your shell or load `.env` through your process manager; the application deliberately does not load secret files implicitly.

Create or upgrade the database before creating a staff account:

```bash
alembic upgrade head
alembic current
```

Create a local staff user with a fake password:

```bash
export STAFF_USERNAME=registrar
export STAFF_PASSWORD='replace-with-a-long-test-password'
python scripts/create_staff_user.py
```

Start the development server:

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` for student registration and `http://127.0.0.1:8000/staff/login` for staff access.

### Existing fake development databases

Alembic is authoritative for schema changes. For an old disposable SQLite database containing fake data, the safest upgrade is to remove the database file and run `alembic upgrade head` again.

If an untouched pre-Alembic database must be retained, back it up first, confirm that it contains only the original `registrations` and `staff_users` schema, then run:

```bash
alembic stamp 0001_initial_schema
alembic upgrade head
```

Do not stamp an unknown or partially modified database. Stamping records a revision without applying its SQL. Use a reviewed migration or restore from backup instead.

## Quality checks

```bash
ruff check .
pytest --cov=app --cov-report=term-missing --cov-fail-under=85
pip-audit -r requirements.txt
python -m build
```

## Configuration

| Variable | Development default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Set to `production` to enable production safety checks. |
| `DATABASE_URL` | `sqlite:///./hsk_registration.db` | SQLAlchemy database URL. |
| `SESSION_SECRET` | Development-only value | Signs staff sessions. Production requires at least 32 characters. |
| `STAFF_USERNAME` | None | One-time staff bootstrap input. |
| `STAFF_PASSWORD` | None | One-time staff bootstrap input; minimum 12 characters. |

The committed `.env.example` contains names and safe placeholders only. `.env` files, databases, private keys, Word templates, and generated documents are ignored by Git.

## Security boundaries

- Public success pages expose only a random registration code.
- Registration details are available only after staff authentication.
- Only active users with the `REGISTRATION_STAFF` role may correct or decide a registration.
- Passwords are Argon2id hashes; plaintext passwords are never stored.
- Authentication failures use the same response for unknown users and wrong passwords.
- Session cookies are HTTP-only, `SameSite=Lax`, and `Secure` in production.
- Every staff POST uses a random CSRF token bound to the signed session; login rotates the session and token.
- Edits and decisions require the version displayed to staff, so a stale browser cannot overwrite newer work.
- Only `PENDING` registrations can change. `VERIFIED` and `REJECTED` records are terminal and read-only.
- Each accepted correction or decision and its audit row commit in one transaction.
- Audit rows record the action and changed field names, never old or new passport, birth-date, or phone values.
- Responses deny framing and unnecessary browser capabilities and use a restrictive content security policy.
- Submitted passport and phone values are not written to application logs or validation pages.

The application does not currently implement login throttling. A reverse proxy or identity-aware gateway must rate-limit `/staff/login` before any network deployment.

## Production migration rule

Production startup never creates or alters tables. An operator must run `alembic upgrade head` as a separate deployment step before starting the new application version. Back up the database first, run migrations with a restricted deployment identity, verify `alembic current`, and keep application database credentials unable to change schema where the database platform supports that separation.

## Before any real deployment

SQLite and the local Uvicorn command are for fake-data demonstrations. Do not expose this prototype publicly or enter real student information. Institutional deployment requires, at minimum:

- an approved privacy impact assessment and lawful data-handling basis;
- PostgreSQL with restricted credentials and encrypted backups;
- HTTPS at every external boundary and managed secret storage;
- broader account lifecycle controls, administrative role management, and login throttling;
- operational monitoring for repeated authorization, CSRF, and concurrency failures without logging submitted identity values;
- periodic review and export controls for the audit trail;
- retention, deletion, backup-restore, incident-response, and access-review procedures;
- vulnerability monitoring, production logging with verified redaction, and an independent security review.

The design and implementation plan are under `docs/superpowers/`.
