# Verified Registration DOCX Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let authorized registration staff download a polished, in-memory Word record for a verified registration, with strict template validation and a redacted audit event for every successful generation.

**Architecture:** A packaged DOCX template defines the editable presentation, while a focused document service validates and fills isolated placeholder runs without touching the database. The staff route enforces authentication, role, CSRF, and verified status; resolves the original verifier; generates bytes before committing a `DOCUMENT_GENERATED` audit row; and returns a no-store attachment only after that commit succeeds.

**Tech Stack:** Python 3.12–3.14, FastAPI, SQLAlchemy 2, Alembic, SQLite, Jinja2, python-docx 1.2.0, lxml 6.1.3, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-10-02-docx-generation-design.md`

## Global Constraints

- Work directly on `main`; every task ends with a human-readable commit and `git push origin main`.
- Use fake candidate data only in tests, rendered examples, logs, and documentation.
- Never persist generated candidate documents; runtime output is built in `io.BytesIO` and returned as bytes.
- Only active users with role `REGISTRATION_STAFF` may generate a document, and only when the registration status is exactly `VERIFIED`.
- Use the safe filename `hsk_registration_<REGISTRATION_CODE>.docx`; never include a candidate name or passport number.
- The template must contain each required placeholder exactly once in one complete text run and contain no unknown placeholder.
- A successful download must correspond to a committed, redacted `DOCUMENT_GENERATED` audit row; any generation or commit failure returns no document.
- The default template is packaged at `app/document_templates/hsk_registration_template.docx`; `DOCUMENT_TEMPLATE_PATH` may override it.
- Pin `python-docx==1.2.0` and its locked transitive dependency `lxml==6.1.3` in the project dependency files.
- Do not describe the generated record as an official Chinese Testing International form.

## Review Focus

- A placeholder split across two Word runs must fail closed instead of silently producing a partially filled document; Task 3 adds this service test.
- A verified record whose original verifier no longer resolves must return a generic service failure with no audit row or candidate data leakage; Task 4 adds this route test.
- Two legitimate downloads of the same verified record must each work and create distinct redacted audit rows; Task 4 adds this route test.
- A database failure while saving the audit event must prevent the attachment response; Task 4 adds this transaction-failure test.
- A built wheel installed outside the repository must still resolve and use the bundled default template; Task 5 adds this clean-install check.

---

### Task 1: Template Configuration and Reproducible Document Artifact

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `scripts/build_document_template.py`
- Create: `tests/test_document_template.py`
- Create: `app/document_templates/hsk_registration_template.docx`

**Interfaces:**
- Consumes: `Settings.from_env(environ: Mapping[str, str] | None = None) -> Settings`
- Produces: `Settings.document_template_path: Path`, `build_template(output_path: Path) -> None`, and the exact packaged template contract from the specification

- [ ] **Step 1: Write failing configuration tests**

Add `test_default_document_template_path_is_package_relative` and `test_document_template_path_can_be_overridden` to `tests/test_config.py`. Assert that the default equals `Path(app.__file__).parent / "document_templates/hsk_registration_template.docx"`, while a supplied `DOCUMENT_TEMPLATE_PATH` is expanded and resolved to an absolute `Path`.

- [ ] **Step 2: Run the configuration tests and verify RED**

Run: `.venv/bin/pytest tests/test_config.py -v`

Expected: FAIL because `Settings` has no `document_template_path` field.

- [ ] **Step 3: Implement template-path configuration**

Extend `Settings` with a defaulted `document_template_path: Path` so existing explicit test/application constructors remain compatible, and update `Settings.from_env` to supply overrides. Resolve the default from the installed `app` package directory, not the process working directory. Resolve an override with `Path.expanduser().resolve()` without requiring the path to exist during settings construction.

- [ ] **Step 4: Run configuration tests and the full suite**

Run: `.venv/bin/pytest tests/test_config.py -v && .venv/bin/pytest -q`

Expected: all tests PASS.

- [ ] **Step 5: Add dependency and packaging declarations**

Add `python-docx==1.2.0` to `pyproject.toml` and `requirements.txt`, add `lxml==6.1.3` to the locked transitive dependencies, and include `document_templates/*.docx` in `[tool.setuptools.package-data]`. Update `.gitignore` so the single application template can be committed while arbitrary generated DOCX files remain ignored.

- [ ] **Step 6: Install the locked dependency update**

Run: `.venv/bin/python -m pip install -r requirements-dev.txt && .venv/bin/python -m pip install -e .`

Expected: installation succeeds without resolver warnings.

- [ ] **Step 7: Write the failing template-contract test**

In `tests/test_document_template.py`, add `test_bundled_template_has_exact_isolated_placeholders`. Open the template with `python-docx`; recursively inspect body paragraphs and table cells; assert the required set is present exactly once, each placeholder occupies a complete run, and no unknown `{{...}}` token exists.

- [ ] **Step 8: Run the template test and verify RED**

Run: `.venv/bin/pytest tests/test_document_template.py -v`

Expected: FAIL because the builder and bundled template do not exist.

- [ ] **Step 9: Build the real template with the documents workflow**

Read the documents skill's create, render-verification, privacy-metadata, writing-quality, and relevant accessibility instructions. Load the workspace document runtime. Immediately before the first DOCX authoring command, run the required artifact-operation marker exactly once. Implement `build_template(output_path: Path) -> None` in `scripts/build_document_template.py`, then generate `app/document_templates/hsk_registration_template.docx` with the approved one-page layout and exact isolated placeholders.

- [ ] **Step 10: Render and inspect the blank template**

Use the workspace-provided `render_docx.py` to render every page to PNG. Inspect each image at full resolution for clipping, overflow, weak contrast, broken tables, unresolved layout artifacts, accidental blank pages, and misleading official branding. If the builder changes, rebuild and rerender until the one-page output is clean.

- [ ] **Step 11: Run template, quality, and dependency checks**

Run: `.venv/bin/pytest tests/test_config.py tests/test_document_template.py -v && .venv/bin/ruff check . && .venv/bin/pip-audit -r requirements.txt`

Expected: all tests PASS, Ruff reports no issues, and pip-audit reports no known vulnerabilities.

- [ ] **Step 12: Commit and push**

```bash
git add .gitignore app/config.py app/document_templates/hsk_registration_template.docx pyproject.toml requirements.txt scripts/build_document_template.py tests/test_config.py tests/test_document_template.py
git commit -m "feat: add the registration document template"
git push origin main
```

### Task 2: Auditable Document-Generation Action

**Files:**
- Modify: `app/models.py`
- Create: `alembic/versions/0003_document_generation.py`
- Modify: `tests/test_migrations.py`
- Create: `tests/test_document_audit.py`

**Interfaces:**
- Consumes: `AuditAction`, `AuditLog`, Alembic revision `0002_staff_verification`
- Produces: `AuditAction.DOCUMENT_GENERATED` and migration revision `0003_document_generation`

- [ ] **Step 1: Write failing model and migration tests**

Add a model test asserting `AuditAction.DOCUMENT_GENERATED.value == "DOCUMENT_GENERATED"`. Extend migration tests to assert: a blank database reaches `0003_document_generation`; existing `0002` audit rows survive upgrade; the database accepts `DOCUMENT_GENERATED`; downgrade succeeds when no new-action rows exist; and downgrade raises a clear error without deleting data when a new-action row exists.

- [ ] **Step 2: Run the targeted tests and verify RED**

Run: `.venv/bin/pytest tests/test_document_audit.py tests/test_migrations.py -v`

Expected: FAIL because the enum member and revision do not exist.

- [ ] **Step 3: Add the enum member and safe SQLite migration**

Add `DOCUMENT_GENERATED` to `AuditAction`. Create `0003_document_generation.py` using Alembic batch table recreation so upgrade widens the `audit_action` check while preserving rows, foreign keys, indexes, JSON values, and timestamps. Before downgrade, query for `DOCUMENT_GENERATED` and raise `RuntimeError` if any exist; otherwise recreate the prior constraint.

- [ ] **Step 4: Run migration tests and the full suite**

Run: `.venv/bin/pytest tests/test_document_audit.py tests/test_migrations.py -v && .venv/bin/pytest -q`

Expected: all tests PASS.

- [ ] **Step 5: Commit and push**

```bash
git add app/models.py alembic/versions/0003_document_generation.py tests/test_document_audit.py tests/test_migrations.py
git commit -m "feat: track generated registration documents"
git push origin main
```

### Task 3: Strict In-Memory DOCX Generation Service

**Files:**
- Create: `app/services/document_service.py`
- Create: `tests/test_document_service.py`

**Interfaces:**
- Consumes: `Registration`, `Path`, the packaged template contract
- Produces: `DocumentTemplateError`, `generate_registration_document(registration: Registration, verified_by_username: str, template_path: Path) -> bytes`

- [ ] **Step 1: Write the failing happy-path service test**

Add `test_generate_registration_document_returns_valid_docx_with_fake_values`. Use a verified fake `Registration`, call the wished-for API, reopen the returned bytes with `python-docx`, and assert all eleven formatted values appear, no `{{...}}` token remains, the privacy notice remains, an emphasized label retains its formatting, and no DOCX file is created in the working directory.

- [ ] **Step 2: Run the happy-path test and verify RED**

Run: `.venv/bin/pytest tests/test_document_service.py::test_generate_registration_document_returns_valid_docx_with_fake_values -v`

Expected: FAIL because `app.services.document_service` does not exist.

- [ ] **Step 3: Implement the minimal service API**

Create `DocumentTemplateError` and `generate_registration_document(...) -> bytes`. Walk body and nested table paragraphs, require each exact token in one complete run, replace only that run's text, format date as ISO `YYYY-MM-DD`, format `verified_at` as UTC ISO text, save to `io.BytesIO`, and return its bytes.

- [ ] **Step 4: Run the happy-path test and verify GREEN**

Run: `.venv/bin/pytest tests/test_document_service.py::test_generate_registration_document_returns_valid_docx_with_fake_values -v`

Expected: PASS.

- [ ] **Step 5: Write failing contract and metadata tests**

Add focused tests for a missing template file, malformed DOCX, missing placeholder, duplicate placeholder, unknown placeholder, and a required placeholder split across runs. Add `test_generated_document_scrubs_personal_build_metadata`, seeding core and extended properties with fake developer/machine values and asserting they are absent from the returned archive.

- [ ] **Step 6: Run the new tests and verify RED**

Run: `.venv/bin/pytest tests/test_document_service.py -v`

Expected: the malformed-contract and metadata cases FAIL for their intended missing behavior.

- [ ] **Step 7: Complete strict validation and metadata scrubbing**

Implement exact token counting, split-run detection using paragraph text versus run text, unknown-token detection, generic exception translation to `DocumentTemplateError`, and metadata clearing. Scrub core properties through `python-docx` and extended application properties through the DOCX ZIP XML without changing document content or emitting candidate values in errors.

- [ ] **Step 8: Run service tests and the full suite**

Run: `.venv/bin/pytest tests/test_document_service.py -v && .venv/bin/pytest -q`

Expected: all tests PASS.

- [ ] **Step 9: Commit and push**

```bash
git add app/services/document_service.py tests/test_document_service.py
git commit -m "feat: generate verified registration documents"
git push origin main
```

### Task 4: Protected Staff Download Workflow

**Files:**
- Modify: `app/routes/staff.py`
- Modify: `app/templates/staff_registration.html`
- Modify: `app/static/styles.css`
- Create: `tests/test_staff_documents.py`

**Interfaces:**
- Consumes: `generate_registration_document(...) -> bytes`, `AuditAction.DOCUMENT_GENERATED`, existing `RegistrationStaff` and CSRF dependencies
- Produces: `POST /staff/registrations/{code}/document` returning a DOCX attachment after a successful audit commit

- [ ] **Step 1: Write failing verified-download and UI tests**

Add tests asserting that a verified detail page shows the document form, the form contains the session CSRF token, and a valid POST returns status `200`, DOCX content type, `attachment; filename="hsk_registration_<CODE>.docx"`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, and valid DOCX bytes. Assert the response filename contains neither fake name nor passport value.

- [ ] **Step 2: Run the happy-path route tests and verify RED**

Run: `.venv/bin/pytest tests/test_staff_documents.py -v`

Expected: FAIL because the route and interface action do not exist.

- [ ] **Step 3: Implement the minimal protected route and interface action**

Add the POST route guarded by `RegistrationStaff`; parse and validate CSRF before record lookup; normalize and load by public code; return `404` for unknown records; return a generic `409` for any non-verified state; load the username identified by `registration.verified_by`; call the document service with `request.app.state.settings.document_template_path`; add a redacted `AuditLog(action=DOCUMENT_GENERATED, changed_fields=[])`; commit; and only then return a `Response` with the required DOCX headers. Show the form only for `VERIFIED` records.

- [ ] **Step 4: Run the happy-path route tests and verify GREEN**

Run: `.venv/bin/pytest tests/test_staff_documents.py -v`

Expected: the happy-path and UI tests PASS.

- [ ] **Step 5: Write failing authorization, state, audit, and failure tests**

Add separate tests for anonymous access, inactive users, `VIEW_ONLY` users, missing and incorrect CSRF tokens, unknown code, `PENDING`, `REJECTED`, a missing original verifier, missing/malformed template, two successful downloads, and an injected audit-commit failure. Assert unauthorized responses never contain candidate details; unsuccessful requests return no DOCX bytes and create no generation audit; successful audit rows contain `changed_fields == []`; repeated success produces two distinct generation rows.

- [ ] **Step 6: Run the failure-path tests and verify RED**

Run: `.venv/bin/pytest tests/test_staff_documents.py -v`

Expected: uncovered failure paths FAIL for their intended missing handling.

- [ ] **Step 7: Complete safe route error and transaction handling**

Translate `DocumentTemplateError` or a missing verifier into a generic `503 Service Unavailable` response without candidate values, document internals, or filesystem paths. Roll back and re-raise database errors so the existing SQLAlchemy handler returns its generic `500`; ensure no attachment response is constructed before commit succeeds. Log only a fixed diagnostic message for template failures.

- [ ] **Step 8: Run route tests and the full suite**

Run: `.venv/bin/pytest tests/test_staff_documents.py -v && .venv/bin/pytest -q`

Expected: all tests PASS.

- [ ] **Step 9: Commit and push**

```bash
git add app/routes/staff.py app/templates/staff_registration.html app/static/styles.css tests/test_staff_documents.py
git commit -m "feat: let staff download verified Word records"
git push origin main
```

### Task 5: Operational Documentation, Package Proof, and Final Visual QA

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `tests/test_package_data.py`

**Interfaces:**
- Consumes: the installed `app` package, `Settings.from_env`, and the complete staff document workflow
- Produces: verified distribution packaging and operator instructions for `DOCUMENT_TEMPLATE_PATH`

- [ ] **Step 1: Write the failing package-data test**

Add `test_distributions_contain_default_document_template`. Build the wheel and source distribution into a temporary directory, inspect both archives, and assert they contain `app/document_templates/hsk_registration_template.docx`. Add a subprocess check that installs the wheel with `--no-deps` into a clean temporary target, changes outside the repository, imports `Settings`, and confirms the default path exists and can generate a fake-data document.

- [ ] **Step 2: Run the package test and verify its pre-documentation state**

Run: `.venv/bin/pytest tests/test_package_data.py -v`

Expected: PASS if Task 1 packaging is correct; if it fails, fix package-data configuration before continuing and rerun until PASS. This is a distribution-level proof, not a new runtime behavior test.

- [ ] **Step 3: Update operational documentation**

Document the verified-only Word workflow, in-memory generation, redacted audit behavior, safe handling after download, default template, `DOCUMENT_TEMPLATE_PATH` override, template-contract rules, rebuild command, and visual-review requirement. Update the milestone list so DOCX generation is no longer described as out of scope. Add a commented safe example path to `.env.example` without a real local username or secret.

- [ ] **Step 4: Generate and inspect a fake-data example**

Create a generated DOCX in a temporary QA directory using the service and obviously fake values. Render every page with the workspace `render_docx.py` workflow and inspect at full resolution for clipping, overflow, accidental blank pages, broken tables, unresolved placeholders, and privacy/branding errors. Do not commit the generated example or rendered QA images.

- [ ] **Step 5: Run final verification**

Run:

```bash
.venv/bin/ruff check .
.venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=85
.venv/bin/pip-audit -r requirements.txt
.venv/bin/python -m build
git diff --check
git status --short --branch
```

Expected: Ruff is clean; all tests pass at or above 85% coverage; pip-audit reports no known vulnerabilities; source and wheel builds succeed; `git diff --check` is clean; only the intended documentation and package-test changes remain before commit.

- [ ] **Step 6: Commit and push**

```bash
git add .env.example README.md tests/test_package_data.py
git commit -m "docs: explain secure document generation"
git push origin main
```

- [ ] **Step 7: Verify the remote result**

Run: `git status --short --branch && git log -5 --oneline && git ls-remote --heads origin main`

Expected: local `main` is clean and aligned with `origin/main`; the remote main SHA matches local `HEAD`.
