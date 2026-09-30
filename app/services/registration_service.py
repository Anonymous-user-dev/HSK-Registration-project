import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Registration, RegistrationStatus
from app.schemas import RegistrationCreate

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_PATTERN = re.compile(r"^HSK-[A-Z2-9]{6}$")


def _new_registration_code() -> str:
    suffix = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    return f"HSK-{suffix}"


def create_registration(db: Session, data: RegistrationCreate) -> Registration:
    for _ in range(10):
        code = _new_registration_code()
        if db.scalar(
            select(Registration.id).where(Registration.registration_code == code)
        ) is None:
            break
    else:
        raise RuntimeError("unable to allocate a unique registration code")

    registration = Registration(
        registration_code=code,
        status=RegistrationStatus.PENDING,
        **data.model_dump(),
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


def find_registration_by_code(db: Session, code: str) -> Registration | None:
    normalized = code.strip().upper()
    if CODE_PATTERN.fullmatch(normalized) is None:
        return None
    return db.scalar(
        select(Registration).where(Registration.registration_code == normalized)
    )
