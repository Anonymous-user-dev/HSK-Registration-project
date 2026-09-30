import re
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import RegistrationStatus
from app.schemas import RegistrationCreate
from app.services.registration_service import (
    create_registration,
    find_registration_by_code,
)


def registration_data(**overrides: object) -> RegistrationCreate:
    values: dict[str, object] = {
        "first_name": "Mei",
        "last_name": "Lin",
        "date_of_birth": date(2002, 5, 14),
        "nationality": "Tajikistani",
        "passport_number": "FAKE12345",
        "phone_number": "+992 900 000 001",
        "parent_phone_number": "+992 900 000 002",
        "hsk_level": "HSK3",
    }
    values.update(overrides)
    return RegistrationCreate.model_validate(values)


def test_create_registration_persists_pending_record(db: Session) -> None:
    registration = create_registration(db, registration_data())

    assert registration.id is not None
    assert registration.status is RegistrationStatus.PENDING
    assert registration.first_name == "Mei"
    assert re.fullmatch(r"HSK-[A-Z2-9]{6}", registration.registration_code)


def test_registration_codes_are_unique(db: Session) -> None:
    codes = {
        create_registration(
            db, registration_data(passport_number=f"FAKE{i:05d}")
        ).registration_code
        for i in range(40)
    }

    assert len(codes) == 40


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_name", "   "),
        ("last_name", ""),
        ("nationality", " "),
        ("passport_number", ""),
        ("phone_number", "abc"),
        ("parent_phone_number", " "),
        ("hsk_level", "HSK99"),
        ("hsk_level", "hsk3"),
    ],
)
def test_registration_rejects_invalid_input(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        registration_data(**{field: value})


def test_find_registration_normalizes_code(db: Session) -> None:
    registration = create_registration(db, registration_data())

    lowercase_code = registration.registration_code.lower()
    found = find_registration_by_code(db, f"  {lowercase_code} ")

    assert found is not None
    assert found.id == registration.id


def test_find_registration_returns_none_for_malformed_or_unknown_code(
    db: Session,
) -> None:
    assert find_registration_by_code(db, "not-a-code") is None
    assert find_registration_by_code(db, "HSK-ZZZZZZ") is None


def test_database_rejects_invalid_registration_status(db: Session) -> None:
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                """
                INSERT INTO registrations (
                    registration_code, first_name, last_name, date_of_birth,
                    nationality, passport_number, phone_number,
                    parent_phone_number, hsk_level, status, created_at
                ) VALUES (
                    'HSK-ABC234', 'Mei', 'Lin', '2002-05-14', 'Tajikistani',
                    'FAKE99999', '+992900000001', '+992900000002',
                    'HSK3', 'INVALID', CURRENT_TIMESTAMP
                )
                """
            )
        )
        db.commit()
