from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import StaffUser
from app.security import hash_password, verify_password

_DUMMY_PASSWORD_HASH = hash_password("authentication-timing-placeholder")


def normalize_username(username: str) -> str:
    return username.strip().lower()


def authenticate_staff(
    db: Session, username: str, password: str
) -> StaffUser | None:
    user = db.scalar(
        select(StaffUser).where(StaffUser.username == normalize_username(username))
    )
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password, password_hash)

    if user is None or not password_is_valid or not user.is_active:
        return None
    return user
