# HSK Pre-Registration and Verification System

A security-first prototype that moves repetitive registration typing away from the institute desk. Students submit their information before arrival; authenticated staff retrieve it and compare it with the physical passport.

> **Prototype safety rule:** use fake data only. This repository is not approved to hold real passport numbers, birth dates, or phone numbers.

## What this milestone includes

- Public student pre-registration form
- Server-side Pydantic validation and database constraints
- Cryptographically random public registration codes
- Code-only public confirmation page
- Argon2 password hashing and signed staff sessions
- Authenticated, read-only staff lookup
- SQLite persistence for local demonstration
- Automated tests, linting, coverage, and dependency auditing

Editing, verification/rejection, audit events, DOCX generation, payments, passport images, OCR, and AI are intentionally outside this milestone.

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

## Quality checks

```bash
ruff check .
pytest --cov=app --cov-report=term-missing --cov-fail-under=85
pip-audit -r requirements.txt
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
- Passwords are Argon2id hashes; plaintext passwords are never stored.
- Authentication failures use the same response for unknown users and wrong passwords.
- Session cookies are HTTP-only, `SameSite=Lax`, and `Secure` in production.
- Responses deny framing and unnecessary browser capabilities and use a restrictive content security policy.
- Submitted passport and phone values are not written to application logs or validation pages.

The application does not currently implement login throttling. A reverse proxy or identity-aware gateway must rate-limit `/staff/login` before any network deployment.

## Before any real deployment

SQLite and the local Uvicorn command are for fake-data demonstrations. Do not expose this prototype publicly or enter real student information. Institutional deployment requires, at minimum:

- an approved privacy impact assessment and lawful data-handling basis;
- PostgreSQL with restricted credentials and encrypted backups;
- HTTPS at every external boundary and managed secret storage;
- staff authorization roles, account lifecycle controls, and login throttling;
- CSRF protection for future state-changing staff actions;
- auditable edits and state transitions;
- retention, deletion, backup-restore, incident-response, and access-review procedures;
- vulnerability monitoring, production logging with verified redaction, and an independent security review.

The design and implementation plan are under `docs/superpowers/`.
