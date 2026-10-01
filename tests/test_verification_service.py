from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuditAction,
    AuditLog,
    Registration,
    RegistrationStatus,
    StaffUser,
)
from app.schemas import RegistrationCreate, RegistrationUpdate
from app.security import hash_password
from app.services.registration_service import create_registration
from app.services.verification_service import (
    RegistrationConflictError,
    RegistrationNotFoundError,
    RegistrationStateError,
    reject_registration,
    update_pending_registration,
    verify_registration,
)


def registration_values(**overrides: object) -> dict[str, object]:
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
    return values


def seed_staff_and_registration(db: Session) -> tuple[StaffUser, Registration]:
    staff = StaffUser(
        username="registrar",
        password_hash=hash_password("fake-password-for-tests"),
        role="REGISTRATION_STAFF",
        is_active=True,
    )
    db.add(staff)
    db.commit()
    registration = create_registration(
        db, RegistrationCreate.model_validate(registration_values())
    )
    return staff, registration


def update_data(**overrides: object) -> RegistrationUpdate:
    return RegistrationUpdate.model_validate(registration_values(**overrides))


def test_update_changes_allowed_fields_and_writes_redacted_audit(
    db: Session,
) -> None:
    staff, registration = seed_staff_and_registration(db)

    updated = update_pending_registration(
        db,
        registration.id,
        staff.id,
        registration.version,
        update_data(
            first_name="Meilin",
            passport_number="FAKE-54321",
            phone_number="+992 900 000 099",
            hsk_level="HSK4",
        ),
    )

    assert updated.first_name == "Meilin"
    assert updated.passport_number == "FAKE-54321"
    assert updated.phone_number == "+992 900 000 099"
    assert updated.hsk_level.value == "HSK4"
    assert updated.registration_code == registration.registration_code
    assert updated.status is RegistrationStatus.PENDING
    assert updated.version == 2
    audit = db.scalar(select(AuditLog))
    assert audit is not None
    assert audit.action is AuditAction.REGISTRATION_EDITED
    assert audit.registration_id == registration.id
    assert audit.staff_user_id == staff.id
    assert audit.changed_fields == [
        "first_name",
        "hsk_level",
        "passport_number",
        "phone_number",
    ]
    serialized_audit = json.dumps(audit.changed_fields)
    assert "FAKE-54321" not in serialized_audit
    assert "+992 900 000 099" not in serialized_audit


def test_unchanged_update_creates_no_audit_and_keeps_version(db: Session) -> None:
    staff, registration = seed_staff_and_registration(db)

    unchanged = update_pending_registration(
        db,
        registration.id,
        staff.id,
        registration.version,
        update_data(),
    )

    assert unchanged.version == 1
    assert db.scalar(select(AuditLog)) is None


@pytest.mark.parametrize(
    "status", [RegistrationStatus.VERIFIED, RegistrationStatus.REJECTED]
)
def test_terminal_registration_cannot_be_edited(
    db: Session, status: RegistrationStatus
) -> None:
    staff, registration = seed_staff_and_registration(db)
    registration.status = status
    db.commit()

    with pytest.raises(RegistrationStateError):
        update_pending_registration(
            db,
            registration.id,
            staff.id,
            registration.version,
            update_data(first_name="Changed"),
        )

    db.refresh(registration)
    assert registration.first_name == "Mei"
    assert db.scalar(select(AuditLog)) is None


def test_stale_update_cannot_overwrite_newer_data(db: Session) -> None:
    staff, registration = seed_staff_and_registration(db)
    registration.first_name = "Newer"
    registration.version = 2
    db.commit()

    with pytest.raises(RegistrationConflictError):
        update_pending_registration(
            db,
            registration.id,
            staff.id,
            expected_version=1,
            data=update_data(first_name="Stale"),
        )

    db.refresh(registration)
    assert registration.first_name == "Newer"
    assert registration.version == 2
    assert db.scalar(select(AuditLog)) is None


def test_missing_registration_is_reported_without_audit(db: Session) -> None:
    staff = StaffUser(
        username="registrar",
        password_hash=hash_password("fake-password-for-tests"),
        role="REGISTRATION_STAFF",
        is_active=True,
    )
    db.add(staff)
    db.commit()

    with pytest.raises(RegistrationNotFoundError):
        update_pending_registration(db, 9999, staff.id, 1, update_data())

    assert db.scalar(select(AuditLog)) is None


def test_unknown_staff_id_rolls_back_registration_update(db: Session) -> None:
    _staff, registration = seed_staff_and_registration(db)

    with pytest.raises(IntegrityError):
        update_pending_registration(
            db,
            registration.id,
            staff_user_id=9999,
            expected_version=registration.version,
            data=update_data(first_name="Should roll back"),
        )

    persisted = db.get(Registration, registration.id)
    assert persisted is not None
    assert persisted.first_name == "Mei"
    assert persisted.version == 1
    assert db.scalar(select(AuditLog)) is None


def test_audit_insert_failure_rolls_back_registration_update(db: Session) -> None:
    staff, registration = seed_staff_and_registration(db)

    def reject_audit_insert(*_args) -> None:
        raise RuntimeError("simulated audit storage failure")

    event.listen(AuditLog, "before_insert", reject_audit_insert)
    try:
        with pytest.raises(RuntimeError, match="simulated audit storage failure"):
            update_pending_registration(
                db,
                registration.id,
                staff.id,
                registration.version,
                update_data(first_name="Should roll back"),
            )
    finally:
        event.remove(AuditLog, "before_insert", reject_audit_insert)

    persisted = db.get(Registration, registration.id)
    assert persisted is not None
    assert persisted.first_name == "Mei"
    assert persisted.version == 1
    assert db.scalar(select(AuditLog)) is None


def test_verify_registration_records_staff_time_version_and_audit(
    db: Session,
) -> None:
    staff, registration = seed_staff_and_registration(db)

    verified = verify_registration(
        db, registration.id, staff.id, registration.version
    )

    assert verified.status is RegistrationStatus.VERIFIED
    assert verified.verified_by == staff.id
    assert verified.verified_at is not None
    assert verified.version == 2
    audit = db.scalar(select(AuditLog))
    assert audit is not None
    assert audit.action is AuditAction.REGISTRATION_VERIFIED
    assert audit.changed_fields == ["status", "verified_at", "verified_by"]


def test_reject_registration_leaves_verification_fields_empty(db: Session) -> None:
    staff, registration = seed_staff_and_registration(db)

    rejected = reject_registration(
        db, registration.id, staff.id, registration.version
    )

    assert rejected.status is RegistrationStatus.REJECTED
    assert rejected.verified_by is None
    assert rejected.verified_at is None
    assert rejected.version == 2
    audit = db.scalar(select(AuditLog))
    assert audit is not None
    assert audit.action is AuditAction.REGISTRATION_REJECTED
    assert audit.changed_fields == ["status"]


def test_stale_transition_is_rejected_without_audit(db: Session) -> None:
    staff, registration = seed_staff_and_registration(db)
    registration.version = 2
    db.commit()

    with pytest.raises(RegistrationConflictError):
        verify_registration(db, registration.id, staff.id, expected_version=1)

    db.refresh(registration)
    assert registration.status is RegistrationStatus.PENDING
    assert db.scalar(select(AuditLog)) is None


def test_terminal_registration_cannot_transition_again(db: Session) -> None:
    staff, registration = seed_staff_and_registration(db)
    verify_registration(db, registration.id, staff.id, registration.version)

    with pytest.raises(RegistrationStateError):
        reject_registration(db, registration.id, staff.id, registration.version)

    assert db.scalar(select(func.count(AuditLog.id))) == 1


def test_audit_insert_failure_rolls_back_verification(db: Session) -> None:
    staff, registration = seed_staff_and_registration(db)

    def reject_audit_insert(*_args) -> None:
        raise RuntimeError("simulated transition audit failure")

    event.listen(AuditLog, "before_insert", reject_audit_insert)
    try:
        with pytest.raises(RuntimeError, match="simulated transition audit failure"):
            verify_registration(db, registration.id, staff.id, registration.version)
    finally:
        event.remove(AuditLog, "before_insert", reject_audit_insert)

    persisted = db.get(Registration, registration.id)
    assert persisted is not None
    assert persisted.status is RegistrationStatus.PENDING
    assert persisted.verified_at is None
    assert persisted.verified_by is None
    assert persisted.version == 1
    assert db.scalar(select(AuditLog)) is None
