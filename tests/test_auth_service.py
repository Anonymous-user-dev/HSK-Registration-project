from sqlalchemy.orm import Session

from app.models import StaffUser
from app.security import hash_password, verify_password
from app.services.auth_service import authenticate_staff


def add_staff(
    db: Session, *, username: str = "registrar", password: str = "correct horse battery"
) -> StaffUser:
    user = StaffUser(
        username=username,
        password_hash=hash_password(password),
        role="REGISTRATION_STAFF",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_password_is_argon2_hashed_and_verifiable() -> None:
    password = "correct horse battery"
    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash) is True
    assert verify_password("incorrect password", password_hash) is False


def test_authenticate_staff_accepts_valid_active_user(db: Session) -> None:
    expected = add_staff(db)

    authenticated = authenticate_staff(db, " REGISTRAR ", "correct horse battery")

    assert authenticated is not None
    assert authenticated.id == expected.id


def test_authenticate_staff_rejects_wrong_password_and_unknown_user(
    db: Session,
) -> None:
    add_staff(db)

    assert authenticate_staff(db, "registrar", "wrong password") is None
    assert authenticate_staff(db, "missing", "wrong password") is None


def test_authenticate_staff_rejects_inactive_user(db: Session) -> None:
    user = add_staff(db)
    user.is_active = False
    db.commit()

    assert authenticate_staff(db, "registrar", "correct horse battery") is None
