from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import StaffUser
from app.schemas import RegistrationCreate
from app.security import hash_password
from app.services.registration_service import create_registration


@pytest.fixture
def lookup_app(tmp_path: Path) -> FastAPI:
    app = create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'lookup.db'}",
            session_secret="test-session-secret-that-is-not-for-production",
            secure_cookies=False,
        )
    )
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
    return app


@pytest.fixture
def authenticated_client(lookup_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(lookup_app) as client:
        response = client.post(
            "/staff/login",
            data={"username": "registrar", "password": "correct horse battery"},
        )
        assert response.status_code == 200
        yield client


def create_fake_registration(app: FastAPI) -> str:
    data = RegistrationCreate.model_validate(
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
    )
    with app.state.session_factory() as db:
        return create_registration(db, data).registration_code


def test_staff_lookup_requires_authentication(lookup_app: FastAPI) -> None:
    code = create_fake_registration(lookup_app)

    with TestClient(lookup_app) as client:
        response = client.get(f"/staff/registrations/{code}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/login"


def test_staff_home_displays_search_form(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/staff")

    assert response.status_code == 200
    assert 'name="code"' in response.text
    assert "Find registration" in response.text


def test_staff_can_view_every_required_registration_field(
    authenticated_client: TestClient, lookup_app: FastAPI
) -> None:
    code = create_fake_registration(lookup_app)

    response = authenticated_client.get(f"/staff/registrations/{code}")

    assert response.status_code == 200
    for expected in (
        code,
        "PENDING",
        "Mei",
        "Lin",
        "2002-05-14",
        "Tajikistani",
        "FAKE12345",
        "+992 900 000 001",
        "+992 900 000 002",
        "HSK3",
    ):
        assert expected in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_staff_lookup_accepts_lowercase_code(
    authenticated_client: TestClient, lookup_app: FastAPI
) -> None:
    code = create_fake_registration(lookup_app)

    response = authenticated_client.get(f"/staff/registrations/{code.lower()}")

    assert response.status_code == 200
    assert code in response.text


def test_malformed_and_unknown_codes_share_generic_not_found_response(
    authenticated_client: TestClient,
) -> None:
    malformed = authenticated_client.get("/staff/registrations/not-a-code")
    unknown = authenticated_client.get("/staff/registrations/HSK-ZZZZZZ")

    assert malformed.status_code == unknown.status_code == 404
    assert malformed.text == unknown.text
    assert "Registration not found" in malformed.text


def test_search_submission_redirects_to_normalized_code(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get(
        "/staff/registrations",
        params={"code": " hsk-abc234 "},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/registrations/HSK-ABC234"
