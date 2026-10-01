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
from app.models import (
    AuditAction,
    AuditLog,
    Registration,
    RegistrationStatus,
    StaffUser,
)
from app.schemas import RegistrationCreate
from app.security import hash_password
from app.services.registration_service import create_registration

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(response) -> str:
    match = CSRF_PATTERN.search(response.text)
    assert match is not None
    return match.group(1)


@pytest.fixture
def transition_app(tmp_path: Path) -> FastAPI:
    app = create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'transitions.db'}",
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
def transition_client(transition_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(transition_app) as client:
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


def transition_form(
    client: TestClient, code: str, version: str = "1"
) -> dict[str, str]:
    detail = client.get(f"/staff/registrations/{code}")
    return {"csrf_token": extract_csrf(detail), "version": version}


def test_pending_detail_shows_all_transition_controls(
    transition_client: TestClient, transition_app: FastAPI
) -> None:
    code = transition_app.state.test_registration_code

    response = transition_client.get(f"/staff/registrations/{code}")

    assert response.status_code == 200
    assert f'action="/staff/registrations/{code}/verify"' in response.text
    assert f'action="/staff/registrations/{code}/reject"' in response.text
    assert 'name="version" value="1"' in response.text
    assert 'name="csrf_token"' in response.text


@pytest.mark.parametrize("action", ["verify", "reject"])
@pytest.mark.parametrize("token", ["", "wrong-token"])
def test_invalid_csrf_blocks_state_transition(
    transition_client: TestClient,
    transition_app: FastAPI,
    action: str,
    token: str,
) -> None:
    code = transition_app.state.test_registration_code

    response = transition_client.post(
        f"/staff/registrations/{code}/{action}",
        data={"csrf_token": token, "version": "1"},
    )

    assert response.status_code == 403
    with transition_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        assert registration.status is RegistrationStatus.PENDING
        assert db.scalar(select(AuditLog)) is None


def test_wrong_role_cannot_transition_or_receive_registration_details(
    transition_app: FastAPI,
) -> None:
    code = transition_app.state.test_registration_code
    with TestClient(transition_app) as client:
        login(client, "viewer")
        token = extract_csrf(client.get(f"/staff/registrations/{code}"))

        response = client.post(
            f"/staff/registrations/{code}/verify",
            data={"csrf_token": token, "version": "1"},
        )

    assert response.status_code == 403
    assert "FAKE12345" not in response.text


def test_verify_route_redirects_and_terminal_page_is_read_only(
    transition_client: TestClient, transition_app: FastAPI
) -> None:
    code = transition_app.state.test_registration_code
    form = transition_form(transition_client, code)

    response = transition_client.post(
        f"/staff/registrations/{code}/verify",
        data=form,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/staff/registrations/{code}"
    detail = transition_client.get(response.headers["location"])
    assert "VERIFIED" in detail.text
    assert "REGISTRATION_VERIFIED" in detail.text
    assert "registrar" in detail.text
    assert "/verify" not in detail.text
    assert "/reject" not in detail.text
    assert "/edit" not in detail.text
    with transition_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        assert registration.verified_at is not None
        assert registration.verified_by is not None
        assert db.scalar(select(func.count(AuditLog.id))) == 1


def test_reject_route_leaves_verification_fields_empty(
    transition_client: TestClient, transition_app: FastAPI
) -> None:
    code = transition_app.state.test_registration_code

    response = transition_client.post(
        f"/staff/registrations/{code}/reject",
        data=transition_form(transition_client, code),
        follow_redirects=False,
    )

    assert response.status_code == 303
    with transition_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        assert registration.status is RegistrationStatus.REJECTED
        assert registration.verified_at is None
        assert registration.verified_by is None
        audit = db.scalar(select(AuditLog))
        assert audit is not None
        assert audit.action is AuditAction.REGISTRATION_REJECTED


def test_stale_transition_returns_conflict_without_changing_state(
    transition_client: TestClient, transition_app: FastAPI
) -> None:
    code = transition_app.state.test_registration_code
    form = transition_form(transition_client, code)
    with transition_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        registration.version = 2
        db.commit()

    response = transition_client.post(
        f"/staff/registrations/{code}/verify", data=form
    )

    assert response.status_code == 409
    assert "Reload the registration" in response.text
    with transition_app.state.session_factory() as db:
        registration = db.scalar(select(Registration))
        assert registration is not None
        assert registration.status is RegistrationStatus.PENDING


def test_repeated_transition_returns_conflict_and_keeps_one_audit(
    transition_client: TestClient, transition_app: FastAPI
) -> None:
    code = transition_app.state.test_registration_code
    form = transition_form(transition_client, code)
    first = transition_client.post(
        f"/staff/registrations/{code}/verify", data=form, follow_redirects=False
    )
    assert first.status_code == 303

    repeated = transition_client.post(
        f"/staff/registrations/{code}/reject", data=form
    )

    assert repeated.status_code == 409
    with transition_app.state.session_factory() as db:
        assert db.scalar(select(func.count(AuditLog.id))) == 1


def test_anonymous_transition_redirects_before_record_lookup(
    transition_app: FastAPI,
) -> None:
    code = transition_app.state.test_registration_code
    with TestClient(transition_app) as client:
        response = client.post(
            f"/staff/registrations/{code}/verify",
            data={"csrf_token": "none", "version": "1"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/login"
