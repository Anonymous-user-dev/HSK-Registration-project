from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import AuditAction, AuditLog, Registration, RegistrationStatus
from app.schemas import RegistrationUpdate

EDITABLE_FIELDS = tuple(RegistrationUpdate.model_fields)


class RegistrationNotFoundError(Exception):
    pass


class RegistrationStateError(Exception):
    pass


class RegistrationConflictError(Exception):
    pass


def update_pending_registration(
    db: Session,
    registration_id: int,
    staff_user_id: int,
    expected_version: int,
    data: RegistrationUpdate,
) -> Registration:
    registration = db.get(Registration, registration_id)
    if registration is None:
        raise RegistrationNotFoundError
    if registration.status is not RegistrationStatus.PENDING:
        raise RegistrationStateError
    if registration.version != expected_version:
        raise RegistrationConflictError

    changes = {
        field: getattr(data, field)
        for field in EDITABLE_FIELDS
        if getattr(registration, field) != getattr(data, field)
    }
    if not changes:
        return registration

    try:
        result = db.execute(
            update(Registration)
            .where(
                Registration.id == registration_id,
                Registration.status == RegistrationStatus.PENDING,
                Registration.version == expected_version,
            )
            .values(**changes, version=Registration.version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            _raise_current_state(db, registration_id, expected_version)

        db.add(
            AuditLog(
                registration_id=registration_id,
                staff_user_id=staff_user_id,
                action=AuditAction.REGISTRATION_EDITED,
                changed_fields=sorted(changes),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(registration)
    return registration


def verify_registration(
    db: Session,
    registration_id: int,
    staff_user_id: int,
    expected_version: int,
) -> Registration:
    return _transition_registration(
        db,
        registration_id,
        staff_user_id,
        expected_version,
        target_status=RegistrationStatus.VERIFIED,
        action=AuditAction.REGISTRATION_VERIFIED,
    )


def reject_registration(
    db: Session,
    registration_id: int,
    staff_user_id: int,
    expected_version: int,
) -> Registration:
    return _transition_registration(
        db,
        registration_id,
        staff_user_id,
        expected_version,
        target_status=RegistrationStatus.REJECTED,
        action=AuditAction.REGISTRATION_REJECTED,
    )


def _transition_registration(
    db: Session,
    registration_id: int,
    staff_user_id: int,
    expected_version: int,
    *,
    target_status: RegistrationStatus,
    action: AuditAction,
) -> Registration:
    registration = db.get(Registration, registration_id)
    if registration is None:
        raise RegistrationNotFoundError
    if registration.status is not RegistrationStatus.PENDING:
        raise RegistrationStateError
    if registration.version != expected_version:
        raise RegistrationConflictError

    is_verified = target_status is RegistrationStatus.VERIFIED
    verified_at = datetime.now(UTC) if is_verified else None
    verified_by = staff_user_id if is_verified else None
    changed_fields = (
        ["status", "verified_at", "verified_by"]
        if is_verified
        else ["status"]
    )

    try:
        result = db.execute(
            update(Registration)
            .where(
                Registration.id == registration_id,
                Registration.status == RegistrationStatus.PENDING,
                Registration.version == expected_version,
            )
            .values(
                status=target_status,
                verified_at=verified_at,
                verified_by=verified_by,
                version=Registration.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            _raise_current_state(db, registration_id, expected_version)

        db.add(
            AuditLog(
                registration_id=registration_id,
                staff_user_id=staff_user_id,
                action=action,
                changed_fields=changed_fields,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(registration)
    return registration


def _raise_current_state(
    db: Session, registration_id: int, expected_version: int
) -> None:
    current = db.get(Registration, registration_id)
    if current is None:
        raise RegistrationNotFoundError
    if current.status is not RegistrationStatus.PENDING:
        raise RegistrationStateError
    if current.version != expected_version:
        raise RegistrationConflictError
    raise RegistrationConflictError
