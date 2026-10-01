from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect, text

from alembic import command
from app.database import create_database_engine


def upgrade_database(database_path: Path) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")


def test_blank_database_upgrades_to_current_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migrated.db"

    upgrade_database(database_path)

    engine = create_database_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "alembic_version",
        "audit_logs",
        "registrations",
        "staff_users",
    }
    assert {column["name"] for column in inspector.get_columns("registrations")} >= {
        "version",
        "verified_at",
        "verified_by",
    }
    assert {column["name"] for column in inspector.get_columns("audit_logs")} == {
        "id",
        "registration_id",
        "staff_user_id",
        "action",
        "changed_fields",
        "created_at",
    }
    assert len(inspector.get_foreign_keys("audit_logs")) == 2
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        default_version = connection.scalar(
            text(
                "SELECT dflt_value FROM pragma_table_info('registrations') "
                "WHERE name = 'version'"
            )
        )
    engine.dispose()

    assert revision == "0002_staff_verification"
    assert default_version == "1"


def test_migrated_database_enforces_audit_foreign_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "foreign-keys.db"
    upgrade_database(database_path)
    engine = create_database_engine(f"sqlite:///{database_path}")

    with engine.connect() as connection:
        foreign_keys_enabled = connection.scalar(text("PRAGMA foreign_keys"))

    engine.dispose()
    assert foreign_keys_enabled == 1
