# Staff Correction and Verification — Design

## Purpose

This milestone changes the staff workflow from read-only lookup to controlled verification. An authenticated staff member can correct a pending registration while comparing it with the physical passport, then mark it `VERIFIED` or `REJECTED`. Every accepted mutation is attributable and auditable.

The milestone does not generate Word documents, accept payments, store passport images, or expose real data. Demonstrations continue to use fake data only.

## Scope

The milestone adds:

1. Alembic database migrations.
2. Optimistic concurrency for registrations.
3. CSRF protection for staff forms.
4. Editing of pending registrations.
5. `PENDING → VERIFIED` and `PENDING → REJECTED` transitions.
6. An audit trail for accepted edits and state changes.

Verified and rejected registrations are terminal and read-only in this milestone.

## Database migrations

Alembic becomes the authoritative mechanism for changing persistent schemas. The first migration represents the current registration and staff-user schema, then adds the fields and table required by this milestone. Tests may continue to build isolated databases from SQLAlchemy metadata, but deployment instructions use `alembic upgrade head`.

Application startup must not silently modify a production schema. Development and test environments may initialize a new SQLite database for convenience; production startup verifies connectivity while migrations remain an explicit operator action.

## Registration concurrency

`registrations` gains a non-null integer `version` beginning at `1`. Each accepted edit or state transition increments it. Staff forms send the version they displayed.

A mutation succeeds only if the persisted registration still has the submitted version. If another staff member changed it first, the service rejects the stale request without overwriting the newer data. The interface tells the staff member to reload and review the current record.

## Audit model

`audit_logs` contains:

- `id`
- `registration_id`
- `staff_user_id`
- `action`
- `changed_fields`
- `created_at`

Allowed actions for this milestone are `REGISTRATION_EDITED`, `REGISTRATION_VERIFIED`, and `REGISTRATION_REJECTED`.

`changed_fields` stores a JSON list of field names, not previous or replacement values. This records what was changed without duplicating passport numbers, dates of birth, or phone numbers into another table.

The registration mutation and corresponding audit row occur in one database transaction. Either both commit or neither does.

## Editing rules

Only authenticated, active staff users with role `REGISTRATION_STAFF` may mutate registrations.

Only `PENDING` registrations may be edited. Editable fields are:

- first name
- last name
- date of birth
- nationality
- passport number
- phone number
- parent phone number
- HSK level

The same Pydantic validation used for student submissions validates staff corrections. Registration code, status, creation timestamp, verification timestamp, and verifier are not editable through the correction form.

Submitting unchanged data performs no database mutation, creates no audit row, and does not increment the version.

## State transitions

The only allowed transitions are:

```text
PENDING -> VERIFIED
PENDING -> REJECTED
```

Verification records the current UTC time and the staff user ID. Rejection leaves verification fields empty. Repeating a transition or attempting to transition a terminal record returns a conflict and creates no audit row.

No document-generation capability is added in this milestone. A later document service must still enforce `status == VERIFIED` independently.

## CSRF protection

Every state-changing staff form carries a random CSRF token bound to the signed staff session. Tokens are created with Python's `secrets` module and compared with `secrets.compare_digest`.

The following POST routes require a valid token:

- `/staff/login`
- `/staff/logout`
- `/staff/registrations/{code}/edit`
- `/staff/registrations/{code}/verify`
- `/staff/registrations/{code}/reject`

Missing or invalid tokens return `403` with a generic error and perform no mutation. A successful login rotates the session and its CSRF token.

## Routes and interface

`GET /staff/login` renders a login form with a CSRF token.

`GET /staff/registrations/{code}` continues to display registration details. Pending records display correction, verify, and reject controls. Terminal records display status and audit information without mutation controls.

`GET /staff/registrations/{code}/edit` renders the correction form for a pending registration.

`POST /staff/registrations/{code}/edit` validates the form, registration version, CSRF token, authorization, and current state before applying changes.

`POST /staff/registrations/{code}/verify` and `/reject` validate the same security boundaries before performing their transition.

Conflict responses use HTTP `409`. Invalid form data uses HTTP `422`. Missing records use the existing generic `404`. CSRF and authorization failures use `403` without revealing record details.

## Service boundaries

Routes parse HTTP input and render responses. They do not implement mutation rules.

`verification_service.py` owns edit validation, optimistic concurrency, state transitions, timestamps, and audit creation. Its operations accept a SQLAlchemy session, registration identifier, staff user, expected version, and validated input where relevant.

`csrf.py` owns token generation and validation. Templates only receive tokens; they do not create them.

## Failure handling

Validation, stale-version, terminal-state, CSRF, authorization, and missing-record failures occur before commit and create no audit event. Unexpected database failures roll back the transaction and use the existing redacted database error response.

Mutation routes use POST/Redirect/GET after success so browser refresh does not repeat an action.

## Testing

Tests must prove:

- migrations upgrade a blank database;
- production startup does not create or alter tables;
- missing or invalid CSRF tokens cannot log in, log out, edit, verify, or reject;
- inactive or wrong-role staff cannot mutate records;
- valid edits change only allowed fields and create one redacted audit row;
- unchanged edits create no audit row and do not increment version;
- stale edits and transitions return conflict without overwriting data;
- terminal records cannot be edited or transitioned again;
- verification sets verifier and timestamp;
- rejection leaves verification fields empty;
- mutation and audit insertion roll back together on database failure;
- sensitive values do not appear in audit rows, public responses, or logs.

## Delivery

Each feature is committed separately with a human-readable commit message and pushed to `main` after its complete test suite passes. GitHub CI must pass on the final `main` commit.
