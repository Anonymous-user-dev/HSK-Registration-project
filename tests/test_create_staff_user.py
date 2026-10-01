from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from alembic import command
from app.models import StaffUser
from scripts.create_staff_user import main


def configure_staff_environment(monkeypatch, database_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("STAFF_USERNAME", "registrar")
    monkeypatch.setenv("STAFF_PASSWORD", "fake-bootstrap-password")


def test_staff_bootstrap_refuses_unmigrated_database(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "blank.db"
    configure_staff_environment(monkeypatch, database_path)

    with pytest.raises(SystemExit, match="alembic upgrade head"):
        main()

    engine = create_engine(f"sqlite:///{database_path}")
    assert inspect(engine).get_table_names() == []
    engine.dispose()


def test_staff_bootstrap_creates_user_after_migration(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "migrated.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    configure_staff_environment(monkeypatch, database_path)

    main()

    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as db:
        user = db.scalar(select(StaffUser))
    engine.dispose()
    assert user is not None
    assert user.username == "registrar"
    assert user.password_hash != "fake-bootstrap-password"
