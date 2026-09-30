from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def web_app(tmp_path: Path) -> FastAPI:
    return create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            session_secret="test-session-secret-that-is-not-for-production",
            secure_cookies=False,
        )
    )


@pytest.fixture
def client(web_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(web_app) as test_client:
        yield test_client


def valid_form(**overrides: str) -> dict[str, str]:
    data = {
        "first_name": "Mei",
        "last_name": "Lin",
        "date_of_birth": "2002-05-14",
        "nationality": "Tajikistani",
        "passport_number": "FAKE12345",
        "phone_number": "+992 900 000 001",
        "parent_phone_number": "+992 900 000 002",
        "hsk_level": "HSK3",
    }
    data.update(overrides)
    return data


def test_student_form_lists_required_fields_and_levels(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    for field in valid_form():
        assert f'name="{field}"' in response.text
    assert '<option value="HSK6">HSK 6</option>' in response.text


def test_valid_registration_redirects_to_code_only_confirmation(
    client: TestClient,
) -> None:
    submitted = valid_form()
    response = client.post("/registrations", data=submitted, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/registration/success/HSK-")

    confirmation = client.get(response.headers["location"])
    assert confirmation.status_code == 200
    assert "Registration received" in confirmation.text
    assert "HSK-" in confirmation.text
    for private_value in (
        submitted["first_name"],
        submitted["passport_number"],
        submitted["phone_number"],
        submitted["parent_phone_number"],
    ):
        assert private_value not in confirmation.text


@pytest.mark.parametrize(
    ("field", "value"),
    [("first_name", "   "), ("hsk_level", "HSK99")],
)
def test_invalid_registration_returns_safe_feedback_without_private_values(
    client: TestClient, field: str, value: str
) -> None:
    submitted = valid_form(**{field: value})
    response = client.post("/registrations", data=submitted)

    assert response.status_code == 422
    assert "Check the highlighted fields" in response.text
    assert submitted["passport_number"] not in response.text
    assert submitted["phone_number"] not in response.text


def test_unknown_success_code_returns_not_found(client: TestClient) -> None:
    response = client.get("/registration/success/HSK-ZZZZZZ")

    assert response.status_code == 404
    assert "Registration not found" in response.text


def test_public_pages_include_security_headers(client: TestClient) -> None:
    response = client.get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == (
        "camera=(), microphone=(), geolocation=()"
    )
    assert "default-src 'self'" in response.headers["content-security-policy"]
