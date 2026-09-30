from fastapi.testclient import TestClient
from sqlalchemy import event

from app.config import Settings
from app.main import create_app


def test_health_endpoint_returns_exact_status() -> None:
    app = create_app(Settings.from_env({}))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert app.state.settings.environment == "development"


def test_app_shutdown_closes_database_connections() -> None:
    app = create_app(Settings.from_env({}))
    closed_connections: list[object] = []
    event.listen(
        app.state.engine,
        "close",
        lambda connection, _record: closed_connections.append(connection),
    )

    with TestClient(app) as client:
        assert client.get("/registration/success/HSK-ZZZZZZ").status_code == 404

    assert closed_connections
