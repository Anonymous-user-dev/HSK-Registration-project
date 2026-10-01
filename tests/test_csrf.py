from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import StaffUser
from app.routes.staff import require_registration_staff
from app.security import hash_password

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf_token(response) -> str:
    match = CSRF_PATTERN.search(response.text)
    assert match is not None
    return match.group(1)


@pytest.fixture
def csrf_app(tmp_path: Path) -> FastAPI:
    app = create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'csrf.db'}",
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

    @app.post("/test/registration-staff")
    def registration_staff_only(
        staff_user: Annotated[StaffUser, Depends(require_registration_staff)],
    ) -> dict[str, str]:
        return {"username": staff_user.username}

    return app


@pytest.fixture
def csrf_client(csrf_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(csrf_app) as client:
        yield client


def login(client: TestClient, username: str = "registrar") -> str:
    before_login = csrf_token(client.get("/staff/login"))
    response = client.post(
        "/staff/login",
        data={
            "username": username,
            "password": "correct horse battery",
            "csrf_token": before_login,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return before_login


def test_csrf_token_is_stable_within_one_session(csrf_client: TestClient) -> None:
    first = csrf_token(csrf_client.get("/staff/login"))
    second = csrf_token(csrf_client.get("/staff/login"))

    assert first == second


def test_login_rejects_missing_and_cross_session_tokens(csrf_app: FastAPI) -> None:
    with TestClient(csrf_app) as first, TestClient(csrf_app) as second:
        first_token = csrf_token(first.get("/staff/login"))
        second.get("/staff/login")

        missing = second.post(
            "/staff/login",
            data={"username": "registrar", "password": "correct horse battery"},
        )
        crossed = second.post(
            "/staff/login",
            data={
                "username": "registrar",
                "password": "correct horse battery",
                "csrf_token": first_token,
            },
        )

    assert missing.status_code == crossed.status_code == 403
    assert missing.json() == crossed.json() == {"detail": "Invalid request token"}


def test_successful_login_rotates_csrf_token(csrf_client: TestClient) -> None:
    before_login = login(csrf_client)

    after_login = csrf_token(csrf_client.get("/staff"))

    assert after_login != before_login


def test_invalid_logout_token_does_not_clear_authenticated_session(
    csrf_client: TestClient,
) -> None:
    login(csrf_client)

    response = csrf_client.post(
        "/staff/logout", data={"csrf_token": "invalid"}, follow_redirects=False
    )

    assert response.status_code == 403
    assert csrf_client.get("/staff", follow_redirects=False).status_code == 200


def test_registration_staff_dependency_denies_wrong_role(
    csrf_client: TestClient,
) -> None:
    login(csrf_client, username="viewer")

    response = csrf_client.post("/test/registration-staff")

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_registration_staff_dependency_denies_user_deactivated_after_login(
    csrf_client: TestClient, csrf_app: FastAPI
) -> None:
    login(csrf_client)
    with csrf_app.state.session_factory() as db:
        user = db.query(StaffUser).filter_by(username="registrar").one()
        user.is_active = False
        db.commit()

    response = csrf_client.post(
        "/test/registration-staff", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/login"
