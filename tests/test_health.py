from fastapi.testclient import TestClient
from sqlalchemy import event, inspect

from app.config import Settings
from app.main import create_app


def development_settings(database_path) -> Settings:
    return Settings.from_env({"DATABASE_URL": f"sqlite:///{database_path}"})


def test_health_endpoint_returns_exact_status(tmp_path) -> None:
    app = create_app(development_settings(tmp_path / "health.db"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert app.state.settings.environment == "development"


def test_app_shutdown_closes_database_connections(tmp_path) -> None:
    app = create_app(development_settings(tmp_path / "shutdown.db"))
    closed_connections: list[object] = []
    event.listen(
        app.state.engine,
        "close",
        lambda connection, _record: closed_connections.append(connection),
    )

    with TestClient(app) as client:
        assert client.get("/registration/success/HSK-ZZZZZZ").status_code == 404

    assert closed_connections


def test_production_startup_does_not_create_database_schema(tmp_path) -> None:
    database_path = tmp_path / "production.db"
    settings = Settings.from_env(
        {
            "APP_ENV": "production",
            "DATABASE_URL": f"sqlite:///{database_path}",
            "SESSION_SECRET": "a-secure-production-secret-with-32-characters",
        }
    )

    app = create_app(settings)

    assert inspect(app.state.engine).get_table_names() == []
    app.state.engine.dispose()
