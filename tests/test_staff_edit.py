from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.main import create_app
from app.models import AuditLog, Registration, RegistrationStatus, StaffUser
from app.schemas import RegistrationCreate
from app.security import hash_password
from app.services.registration_service import create_registration

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(response) -> str:
    match = CSRF_PATTERN.search(response.text)
    assert match is not None
    return match.group(1)


@pytest.fixture
def edit_app(tmp_path: Path) -> FastAPI:
    app = create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'edit.db'}",
            session_secret="test-session-secret-that-is-not-for-production",
            secure_cookies=False,
        )
    )
    with app.state.session_factory() as db:
        db.add_all(
            [
                StaffUser(
                    username="registrar",
                    password_hash=hash_password("correct horse battery"),
                    role="REGISTRATION_STAFF",
                    is_active=True,
                ),
                StaffUser(
                    username="viewer",
                    password_hash=hash_password("correct horse battery"),
                    role="VIEW_ONLY",
                    is_active=True,
                ),
            ]
        )
        db.commit()
        registration = create_registration(
            db,
            RegistrationCreate.model_validate(
                {
                    "first_name": "Mei",
                    "last_name": "Lin",
                    "date_of_birth": "2002-05-14",
                    "nationality": "Tajikistani",
                    "passport_number": "FAKE12345",
                    "phone_number": "+992 900 000 001",
                    "parent_phone_number": "+992 900 000 002",
                    "hsk_level": "HSK3",
                }
            ),
        )
        app.state.test_registration_code = registration.registration_code
    return app


@pytest.fixture
def edit_client(edit_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(edit_app) as client:
        login(client)
        yield client


def login(client: TestClient, username: str = "registrar") -> None:
    token = extract_csrf(client.get("/staff/login"))
    response = client.post(
        "/staff/login",
        data={
            "username": username,
            "password": "correct horse battery",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def valid_edit_form(token: str, **overrides: str) -> dict[str, str]:
    values = {
        "csrf_token": token,
        "version": "1",
        "first_name": "Mei",
        "last_name": "Lin",
        "date_of_birth": "2002-05-14",
        "nationality": "Tajikistani",
        "passport_number": "FAKE12345",
        "phone_number": "+992 900 000 001",
        "parent_phone_number": "+992 900 000 002",
        "hsk_level": "HSK3",
    }
    values.update(overrides)
    return values


def test_edit_form_requires_authentication(edit_app: FastAPI) -> None:
    code = edit_app.state.test_registration_code

    with TestClient(edit_app) as client:
        response = client.get(
            f"/staff/registrations/{code}/edit", follow_redirects=False
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/login"


def test_edit_form_denies_wrong_role_without_disclosing_record(
    edit_app: FastAPI,
) -> None:
    code = edit_app.state.test_registration_code
    with TestClient(edit_app) as client:
        login(client, "viewer")

        response = client.get(f"/staff/registrations/{code}/edit")

    assert response.status_code == 403
    assert "FAKE12345" not in response.text


def test_pending_edit_form_contains_current_values_and_security_fields(
    edit_client: TestClient, edit_app: FastAPI
) -> None:
    code = edit_app.state.test_registration_code

    response = edit_client.get(f"/staff/registrations/{code}/edit")

    assert response.status_code == 200
    assert 'name="version" value="1"' in response.text
    assert 'name="csrf_token"' in response.text
    assert 'value="FAKE12345"' in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("submitted_token", ["", "wrong-token"])
def test_invalid_csrf_cannot_edit_registration(
    edit_client: TestClient,
    edit_app: FastAPI,
    submitted_token: str,
) -> None:
    code = edit_app.state.test_registration_code

    response = edit_client.post(
        f"/staff/registrations/{code}/edit",
        data=valid_edit_form(submitted_token, first_name="Attacker"),
    )

    assert response.status_code == 403
    with edit_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        assert registration.first_name == "Mei"
        assert db.scalar(select(AuditLog)) is None


def test_invalid_form_returns_safe_validation_message_without_mutation(
    edit_client: TestClient, edit_app: FastAPI
) -> None:
    code = edit_app.state.test_registration_code
    token = extract_csrf(edit_client.get(f"/staff/registrations/{code}/edit"))

    response = edit_client.post(
        f"/staff/registrations/{code}/edit",
        data=valid_edit_form(token, passport_number="<invalid passport>"),
    )

    assert response.status_code == 422
    assert "Check the highlighted registration details" in response.text
    assert "&lt;invalid passport&gt;" not in response.text
    with edit_app.state.session_factory() as db:
        assert db.scalar(select(func.count(AuditLog.id))) == 0


def test_successful_edit_redirects_and_creates_one_audit(
    edit_client: TestClient, edit_app: FastAPI
) -> None:
    code = edit_app.state.test_registration_code
    token = extract_csrf(edit_client.get(f"/staff/registrations/{code}/edit"))

    response = edit_client.post(
        f"/staff/registrations/{code}/edit",
        data=valid_edit_form(token, first_name="Meilin"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/staff/registrations/{code}"
    with edit_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        assert registration.first_name == "Meilin"
        assert registration.version == 2
        assert db.scalar(select(func.count(AuditLog.id))) == 1


def test_unchanged_edit_redirects_without_audit_or_version_increment(
    edit_client: TestClient, edit_app: FastAPI
) -> None:
    code = edit_app.state.test_registration_code
    token = extract_csrf(edit_client.get(f"/staff/registrations/{code}/edit"))

    response = edit_client.post(
        f"/staff/registrations/{code}/edit",
        data=valid_edit_form(token),
        follow_redirects=False,
    )

    assert response.status_code == 303
    with edit_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        assert registration.version == 1
        assert db.scalar(select(func.count(AuditLog.id))) == 0


def test_stale_edit_returns_conflict_without_overwriting_newer_data(
    edit_client: TestClient, edit_app: FastAPI
) -> None:
    code = edit_app.state.test_registration_code
    token = extract_csrf(edit_client.get(f"/staff/registrations/{code}/edit"))
    with edit_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        registration.first_name = "Newer"
        registration.version = 2
        db.commit()

    response = edit_client.post(
        f"/staff/registrations/{code}/edit",
        data=valid_edit_form(token, first_name="Stale"),
    )

    assert response.status_code == 409
    assert "Reload the registration" in response.text
    assert "Stale" not in response.text
    with edit_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        assert registration.first_name == "Newer"


@pytest.mark.parametrize(
    "status", [RegistrationStatus.VERIFIED, RegistrationStatus.REJECTED]
)
def test_terminal_registration_edit_form_returns_conflict(
    edit_client: TestClient,
    edit_app: FastAPI,
    status: RegistrationStatus,
) -> None:
    code = edit_app.state.test_registration_code
    with edit_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        registration.status = status
        db.commit()

    response = edit_client.get(f"/staff/registrations/{code}/edit")

    assert response.status_code == 409
    assert "Registration cannot be edited" in response.text


def test_unknown_registration_edit_returns_generic_not_found(
    edit_client: TestClient,
) -> None:
    response = edit_client.get("/staff/registrations/HSK-ZZZZZZ/edit")

    assert response.status_code == 404
    assert "Registration not found" in response.text
