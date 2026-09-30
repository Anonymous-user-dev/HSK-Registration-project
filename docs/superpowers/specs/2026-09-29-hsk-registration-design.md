# HSK Pre-Registration and Verification System — Initial Design

## Purpose

This prototype reduces registration-desk data entry. Students submit their own information before arriving. Institute staff remain responsible for comparing the submission with the physical passport, correcting it when needed, and deciding whether to verify or reject the registration.

The prototype is not the official HSK platform. It does not handle payment, passport images, OCR, or AI. Development and demonstrations use fake data only.

## First milestone

The first vertical slice is deliberately small but production-shaped:

1. A public student page accepts a registration with first name, last name, date of birth, nationality, passport number, phone number, parent phone number, and an HSK level from HSK1–HSK6.
2. FastAPI validates the request with Pydantic and writes a `PENDING` record through SQLAlchemy to SQLite.
3. The application generates a cryptographically random, unique public code such as `HSK-A7M2Q9`.
4. The success page displays only the code, not the submitted personal data.
5. An authenticated staff member can search by code and view the submitted record.

The milestone expressly excludes edits, verification/rejection actions, DOCX generation, exam sessions, and a production deployment. Those features will be added in later, independently tested slices.

## Architecture

The server-rendered application uses FastAPI and Jinja2. Public and staff routes are separate modules. Pydantic request models validate untrusted HTTP input at the edge. SQLAlchemy models provide the persistence mapping and database constraints. Service modules own business decisions such as creating a registration and generating codes, keeping route handlers thin.

```
Browser form
  -> FastAPI route
  -> Pydantic validation
  -> registration service
  -> SQLAlchemy / SQLite
  -> Jinja success or staff-detail template
```

Initial structure:

```
app/
  main.py
  database.py
  models.py
  schemas.py
  security.py
  routes/student.py
  routes/staff.py
  services/registration_service.py
  templates/
  static/
tests/
docs/superpowers/specs/
requirements.txt
README.md
```

## Data model

`registrations` is the central table. It contains an internal integer primary key and an externally visible, unique registration code. Required fields are first name, last name, date of birth, nationality, passport number, phone number, parent phone number, HSK level, status, and creation timestamp. Status is constrained to `PENDING`, `VERIFIED`, or `REJECTED`.

For this first slice, `staff_users` supports authenticated lookup only. It stores a username, an Argon2 password hash, an active flag, role, and timestamps. Initial setup creates a staff account from environment-provided bootstrap values rather than committed credentials.

`audit_logs` is introduced as a schema-compatible interface in the next slice when state-changing staff operations are implemented; there is nothing material to audit beyond initial creation in this slice.

## Security baseline

The application must treat every student submission as untrusted. Validation is performed server-side; HTML attributes only improve usability. The database adds `NOT NULL`, unique registration-code, and status-check constraints.

Sensitive data must not appear in public success pages, application logs, exceptions returned to browsers, tests, sample data, committed configuration, generated filenames, or analytics. Public registration codes use `secrets`, not predictable database IDs. Code lookup is staff-only.

Staff authentication uses Argon2 password hashes and signed, HTTP-only cookies. Secure cookies are enabled in production. Authentication routes use generic error messages, rate limiting is required at the reverse proxy or deployment layer, and every state-changing staff request will require CSRF protection when those actions are introduced.

Configuration comes from environment variables. Production startup must reject missing secret keys and insecure defaults. A committed `.env.example` may document variable names but never values. The repository ignores databases, `.env` files, generated documents, DOCX templates, and private keys.

SQLite is appropriate only for the fake-data prototype. It must not be described as an institutional production datastore. Before real data or public exposure, deployment requires PostgreSQL, HTTPS, restricted database access, encrypted backups, secret management, log redaction, monitoring, retention/deletion rules, incident handling, institutional privacy approval, and a security review.

## State and business rules

Students create only `PENDING` records. Staff actions in the following slice may transition a record from `PENDING` to `VERIFIED` or `REJECTED`. A document-generation service must enforce, in backend code, that only a `VERIFIED` registration can generate an official document. A user interface control alone is not sufficient.

## Errors

Invalid public submissions return field-specific validation feedback without echoing sensitive values. A missing staff lookup returns a generic not-found response. Authentication failures do not reveal whether a username exists. Database failures are logged with safe metadata and returned as a generic server error.

## Tests and verification

The initial test suite covers valid submission persistence, invalid or blank required fields, invalid HSK levels, unique registration-code generation, public confirmation data minimization, unauthenticated staff access denial, authenticated staff lookup, and unknown-code behavior. Later slices add state-transition and document-generation tests before their routes exist.

## Delivery sequence

1. Set up dependency definitions, repository hygiene, and application configuration.
2. Implement and test the student registration flow.
3. Add and test minimal staff authentication and protected lookup.
4. Commit each completed feature independently with tests passing.
5. Add staff correction, verification/rejection, audit logging, and DOCX generation in separate slices.

## Git and delivery safeguards

The repository uses branch `main`, with an initial design commit followed by small feature commits. Before pushing, the remote is set to the user-provided GitHub repository. GitHub branch protection must be enabled in GitHub: require pull requests, passing status checks, and at least one approval where the repository’s account plan permits it. Local Git configuration alone cannot protect the remote branch.
