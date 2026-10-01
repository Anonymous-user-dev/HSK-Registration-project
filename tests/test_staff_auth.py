import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Base, StaffUser
from app.security import hash_password

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf_token(client: TestClient, path: str = "/staff/login") -> str:
    response = client.get(path)
    match = CSRF_PATTERN.search(response.text)
    assert match is not None
    return match.group(1)


def login_data(client: TestClient, username: str, password: str) -> dict[str, str]:
    return {
        "username": username,
        "password": password,
        "csrf_token": csrf_token(client),
    }


@pytest.fixture
def staff_app(tmp_path: Path) -> FastAPI:
    return create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'staff.db'}",
            session_secret="test-session-secret-that-is-not-for-production",
            secure_cookies=False,
        )
    )


@pytest.fixture
def staff_client(staff_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(staff_app) as client:
        yield client


def seed_staff(app: FastAPI) -> None:
    with app.state.session_factory() as db:
        db.add(
            StaffUser(
                username="registrar",
                password_hash=hash_password("correct horse battery"),
                role="REGISTRATION_STAFF",
                is_active=True,
            )
        )
        db.commit()


def test_staff_page_redirects_anonymous_user_to_login(
    staff_client: TestClient,
) -> None:
    response = staff_client.get("/staff", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/login"


def test_login_failure_is_identical_for_unknown_user_and_wrong_password(
    staff_client: TestClient, staff_app: FastAPI
) -> None:
    seed_staff(staff_app)

    unknown = staff_client.post(
        "/staff/login", data=login_data(staff_client, "missing", "wrong")
    )
    wrong = staff_client.post(
        "/staff/login", data=login_data(staff_client, "registrar", "wrong")
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.text == wrong.text
    assert "Invalid username or password" in unknown.text


def test_valid_login_sets_protected_session_cookie(
    staff_client: TestClient, staff_app: FastAPI
) -> None:
    seed_staff(staff_app)

    response = staff_client.post(
        "/staff/login",
        data=login_data(staff_client, "registrar", "correct horse battery"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie
    assert staff_client.get("/staff").status_code == 200


def test_production_session_cookie_is_secure(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            environment="production",
            database_url=f"sqlite:///{tmp_path / 'secure.db'}",
            session_secret="production-session-secret-with-32-characters",
            secure_cookies=True,
        )
    )
    Base.metadata.create_all(app.state.engine)
    seed_staff(app)

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/staff/login",
            data=login_data(client, "registrar", "correct horse battery"),
            follow_redirects=False,
        )

    assert "secure" in response.headers["set-cookie"].lower()
    assert response.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )


def test_logout_clears_staff_session(
    staff_client: TestClient, staff_app: FastAPI
) -> None:
    seed_staff(staff_app)
    staff_client.post(
        "/staff/login",
        data=login_data(staff_client, "registrar", "correct horse battery"),
    )

    response = staff_client.post(
        "/staff/logout",
        data={"csrf_token": csrf_token(staff_client, "/staff")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/login"
    assert staff_client.get("/staff", follow_redirects=False).status_code == 303
