from __future__ import annotations

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
