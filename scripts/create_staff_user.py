import os

from sqlalchemy import Engine, inspect, select, text

from app.config import Settings
from app.database import create_database_engine, create_session_factory
from app.models import StaffUser
from app.security import hash_password
from app.services.auth_service import normalize_username

REQUIRED_DATABASE_REVISION = "0002_staff_verification"


def require_current_database(engine: Engine) -> None:
    if not inspect(engine).has_table("alembic_version"):
        raise SystemExit("Database is not migrated; run: alembic upgrade head")
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    if revision != REQUIRED_DATABASE_REVISION:
        raise SystemExit("Database is not current; run: alembic upgrade head")


def main() -> None:
    username = normalize_username(os.environ.get("STAFF_USERNAME", ""))
    password = os.environ.get("STAFF_PASSWORD", "")
    if not username or len(password) < 12:
        raise SystemExit(
            "STAFF_USERNAME and STAFF_PASSWORD (12+ characters) are required"
        )

    settings = Settings.from_env()
    engine = create_database_engine(settings.database_url)
    try:
        require_current_database(engine)
        factory = create_session_factory(engine)

        with factory() as db:
            if db.scalar(select(StaffUser.id).where(StaffUser.username == username)):
                raise SystemExit("Staff username already exists")
            db.add(
                StaffUser(
                    username=username,
                    password_hash=hash_password(password),
                    role="REGISTRATION_STAFF",
                    is_active=True,
                )
            )
            db.commit()
    finally:
        engine.dispose()

    print(f"Created staff user: {username}")


if __name__ == "__main__":
    main()
