# Verified Registration Document Generation Design

## Purpose

Add a production-minded DOCX export to the staff workflow. The feature turns an already verified registration into a professional, editable Word document while preserving the system's central trust boundary: student-submitted data cannot become an official working document until staff have checked it against physical identification.

This feature does not claim to reproduce an official Chinese Testing International form. It provides a neutral institute working document named **HSK Candidate Registration Record**. The institute can later replace the bundled template with its approved form without changing the verification workflow.

## Scope

The vertical slice includes:

- a polished, one-page DOCX template maintained in the repository;
- a deterministic template-building script so the document can be reproduced and reviewed;
- a document service that validates the template contract and fills it without flattening Word formatting;
- a protected staff endpoint and interface action for generating a document;
- a backend rule that permits generation only for `VERIFIED` registrations;
- a redacted audit event for every successful generation;
- automated tests for the business rule, document contents, access controls, error paths, and response headers;
- visual inspection of both the blank template and a generated fake-data example.

The slice excludes PDF conversion, email delivery, bulk generation, electronic signatures, passport images, OCR, document storage, and claims of compliance with an external official form.

## User Experience

An authenticated, active staff member with the `REGISTRATION_STAFF` role opens a registration detail page. For a verified registration, the page shows a **Generate Word document** button. Selecting it submits a CSRF-protected request and downloads a file named:

```text
hsk_registration_<REGISTRATION_CODE>.docx
```

Pending and rejected registrations do not expose an enabled generation action. The backend independently enforces the same rule and returns HTTP `409 Conflict` for direct attempts.

The response uses the DOCX media type, an attachment disposition, `Cache-Control: no-store`, and `X-Content-Type-Options: nosniff`. It never places passport numbers or names in the filename.

## Document Layout

The generated document is a restrained, one-page, portrait form titled **HSK Candidate Registration Record**. It is visually suitable for printing and editing in Microsoft Word without implying affiliation with an official testing body.

The page contains:

1. A header with the document title, registration code, and verified status.
2. A **Candidate identity** section containing first name, last name, date of birth, nationality, and passport number.
3. A **Contact information** section containing phone and parent phone numbers.
4. An **Examination** section containing HSK level.
5. A **Verification** section containing verification date/time and the staff username.
6. Blank lines for candidate signature, staff signature, date, and office notes.
7. A small privacy notice stating that the record contains sensitive personal information and should be handled only by authorized staff.

The document uses readable typography, sufficient whitespace, repeated table headers where relevant, and accessible high-contrast colors. It avoids decorative graphics that make later institute customization harder.

## Template Contract

The runtime template lives at:

```text
app/document_templates/hsk_registration_template.docx
```

It is included as package data so installed builds behave like source checkouts. A deployment may override it with `DOCUMENT_TEMPLATE_PATH`; an override must satisfy the same contract.

The required placeholders are:

```text
{{REGISTRATION_CODE}}
{{FIRST_NAME}}
{{LAST_NAME}}
{{DATE_OF_BIRTH}}
{{NATIONALITY}}
{{PASSPORT_NUMBER}}
{{PHONE_NUMBER}}
{{PARENT_PHONE_NUMBER}}
{{HSK_LEVEL}}
{{VERIFIED_AT}}
{{VERIFIED_BY}}
```

Each placeholder appears exactly once and occupies one complete Word text run. The service rejects a template when a required placeholder is missing, duplicated, split across runs, or when an unknown placeholder is present. Replacement changes only the placeholder run's text, preserving its existing font, size, emphasis, color, table borders, spacing, and surrounding layout.

The repository also contains `scripts/build_document_template.py`, which deterministically rebuilds the template. The committed DOCX remains the runtime artifact and is visually reviewed whenever the builder changes.

## Components and Responsibilities

### Configuration

Application settings expose a resolved `document_template_path`. The default is based on the installed `app` package location rather than the current working directory. Startup does not parse the document, but generation fails closed if the configured template is absent or invalid.

### Document service

`app/services/document_service.py` owns all DOCX-specific behavior. It:

- validates the exact placeholder set;
- formats dates and timestamps consistently;
- converts a verified registration into replacement values;
- replaces isolated placeholder runs without rewriting complete paragraphs or cells;
- scrubs creator, modifier, company, manager, last-printed, and revision metadata;
- writes the result to `io.BytesIO` and returns bytes;
- raises a domain-specific template error without exposing local paths or parser details to the browser.

The service does not query the database, authorize users, change registration state, or write generated documents to disk.

### Staff route

The staff route owns HTTP and transaction behavior. It loads the registration by public code, requires an authenticated active `REGISTRATION_STAFF` user, validates CSRF, verifies that the status is `VERIFIED`, asks the document service for bytes, adds the audit event, commits, and returns the attachment response.

Authorization and status checks happen before template parsing. Document bytes are created before the audit transaction is committed. If document creation or audit persistence fails, no download is returned. A successful response therefore always corresponds to a committed audit event.

### Audit log

`AuditAction` gains `DOCUMENT_GENERATED`. Its details contain no field values and no document content. A successful event records only the action, registration relationship, acting staff user, timestamp, and a short redacted description.

Repeated downloads are allowed because staff may legitimately need another copy. Every successful generation creates a separate audit entry. Generating a document does not change the registration status or version.

## Data Flow

```text
Staff submits Generate Word document + CSRF token
                      |
                      v
Authentication, active-account, role, and CSRF checks
                      |
                      v
Load registration by public code
                      |
                      v
Require status == VERIFIED
                      |
                      v
Validate template and build DOCX bytes in memory
                      |
                      v
Insert redacted DOCUMENT_GENERATED audit event and commit
                      |
                      v
Return no-store attachment response
```

No generated file is retained by the application. Temporary files used only by development-time rendering tools are kept outside runtime data paths and are not committed.

## Error Handling

- An unknown registration code returns `404 Not Found` without revealing other records.
- A pending or rejected registration returns `409 Conflict` and creates no audit event.
- An unauthenticated request follows the existing staff authentication behavior.
- An inactive or unauthorized account receives the existing authorization response.
- A missing or malformed CSRF token is rejected before generation.
- A missing, unreadable, malformed, or contract-breaking template returns a generic `503 Service Unavailable`, creates no audit event, and logs the diagnostic server-side without including registration field values.
- An audit database failure prevents the download and rolls back the transaction.
- Unexpected exceptions use the application's existing generic error handling and must not disclose filesystem paths, document internals, or personal data.

## Security and Privacy

- Verification is enforced in the service-facing backend path, not only by hiding the button.
- Generated documents exist only in memory during a request and are not cached by the browser response policy.
- Filenames use only the validated public registration code.
- No passport image or additional sensitive field is introduced.
- Template and generation logs contain no candidate field values.
- DOCX metadata is scrubbed so developer usernames, machine names, and build-tool identity do not leak.
- All development examples and visual checks use obviously fake candidate data.
- The output is still sensitive after download; the document itself carries a handling notice for authorized staff.

## Database Migration

A new Alembic revision extends the `audit_logs.action` constraint to accept `DOCUMENT_GENERATED`. SQLite requires the migration to recreate the constrained table safely while preserving existing rows, foreign keys, indexes, and timestamps. The downgrade recreates the prior constraint only after deleting no data; downgrade must fail clearly if document-generation audit rows exist rather than silently discarding history.

## Dependencies and Packaging

`python-docx` is a pinned production dependency. Its security-relevant transitive dependencies remain covered by the existing lock/check workflow. The package configuration includes `app/document_templates/*.docx` in built wheels and source distributions.

The template-building script uses the same document library as runtime generation. Development verification renders DOCX files with the workspace-provided document tooling, not with an untracked desktop-only manual process.

## Testing Strategy

Service tests open the produced DOCX and assert that:

- every fake registration value appears in the correct document structure;
- no template placeholder remains;
- required formatting survives replacement;
- core and extended metadata are scrubbed;
- a missing, duplicate, split, or unknown placeholder is rejected;
- generation does not create a file on disk.

Route tests assert that:

- a verified registration produces a valid DOCX attachment with the expected safe filename and security headers;
- pending and rejected records return `409` with no audit entry;
- authentication, active-user, role, and CSRF protections apply;
- successful repeated generations produce separate redacted audit events;
- template or audit failures return no document and no misleading success event;
- unknown codes return `404`.

Migration tests verify upgrade from the previous revision, preservation of existing audit rows, acceptance of the new action, and downgrade refusal when the new action is present.

Packaging tests build and install the project into a clean environment, then confirm that the default template is available through the installed package.

Before release, both the blank template and a generated fake-data example are rendered to images. Every page is inspected for clipping, overflow, broken tables, accidental blank pages, weak contrast, and unresolved placeholders. Any layout change triggers a fresh render and inspection.

## Acceptance Criteria

The feature is complete when an authorized staff user can download a polished Word document for a verified fake registration; an unverified record cannot produce one through any route; each successful download has a committed redacted audit event; failures do not leave files or false audit history; the DOCX template ships in an installed package; all automated checks pass; and rendered output has been visually inspected page by page.
