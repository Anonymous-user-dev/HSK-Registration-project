from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text

from alembic import command
from app.database import create_database_engine


def migration_config(database_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def upgrade_database(database_path: Path, revision: str = "head") -> None:
    command.upgrade(migration_config(database_path), revision)


def insert_audit_fixture(database_path: Path, action: str) -> None:
    engine = create_database_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO staff_users "
                "(id, username, password_hash, role, is_active, created_at) "
                "VALUES (1, 'registrar', 'fake-hash', 'REGISTRATION_STAFF', 1, "
                "'2026-10-02 10:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO registrations "
                "(id, registration_code, first_name, last_name, date_of_birth, "
                "nationality, passport_number, phone_number, parent_phone_number, "
                "hsk_level, status, created_at, verified_at, verified_by, version) "
                "VALUES (1, 'HSK-FAKE01', 'Mei', 'Lin', '2002-05-14', "
                "'Tajikistani', 'FAKE12345', '+992 900 000 001', "
                "'+992 900 000 002', 'HSK3', 'VERIFIED', "
                "'2026-10-02 09:00:00', '2026-10-02 10:00:00', 1, 2)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO audit_logs "
                "(id, registration_id, staff_user_id, action, changed_fields, "
                "created_at) VALUES (1, 1, 1, :action, '[]', "
                "'2026-10-02 10:00:00')"
            ),
            {"action": action},
        )
    engine.dispose()


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

    assert revision == "0003_document_generation"
    assert default_version == "1"


def test_migrated_database_enforces_audit_foreign_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "foreign-keys.db"
    upgrade_database(database_path)
    engine = create_database_engine(f"sqlite:///{database_path}")

    with engine.connect() as connection:
        foreign_keys_enabled = connection.scalar(text("PRAGMA foreign_keys"))

    engine.dispose()
    assert foreign_keys_enabled == 1


def test_existing_audit_rows_survive_document_action_migration(tmp_path: Path) -> None:
    database_path = tmp_path / "existing-audit.db"
    upgrade_database(database_path, "0002_staff_verification")
    insert_audit_fixture(database_path, "REGISTRATION_VERIFIED")

    upgrade_database(database_path)

    engine = create_database_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT action, changed_fields FROM audit_logs WHERE id = 1")
        ).one()
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    engine.dispose()
    assert row == ("REGISTRATION_VERIFIED", "[]")
    assert revision == "0003_document_generation"


def test_migrated_database_accepts_document_generated_action(tmp_path: Path) -> None:
    database_path = tmp_path / "document-action.db"
    upgrade_database(database_path)

    insert_audit_fixture(database_path, "DOCUMENT_GENERATED")

    engine = create_database_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        action = connection.scalar(text("SELECT action FROM audit_logs WHERE id = 1"))
    engine.dispose()
    assert action == "DOCUMENT_GENERATED"


def test_document_action_migration_downgrades_without_new_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "safe-downgrade.db"
    upgrade_database(database_path)
    insert_audit_fixture(database_path, "REGISTRATION_VERIFIED")

    command.downgrade(migration_config(database_path), "0002_staff_verification")

    engine = create_database_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        action = connection.scalar(text("SELECT action FROM audit_logs WHERE id = 1"))
    engine.dispose()
    assert revision == "0002_staff_verification"
    assert action == "REGISTRATION_VERIFIED"


def test_document_action_migration_refuses_to_discard_new_audit_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "blocked-downgrade.db"
    upgrade_database(database_path)
    insert_audit_fixture(database_path, "DOCUMENT_GENERATED")

    with pytest.raises(RuntimeError, match="DOCUMENT_GENERATED audit rows exist"):
        command.downgrade(migration_config(database_path), "0002_staff_verification")

    engine = create_database_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        action = connection.scalar(text("SELECT action FROM audit_logs WHERE id = 1"))
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    engine.dispose()
    assert action == "DOCUMENT_GENERATED"
    assert revision == "0003_document_generation"
