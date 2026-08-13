from collections.abc import Generator

from app.db.session import get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class ReadySession:
    def execute(self, _statement: object) -> None:
        return None


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers


def test_ready_checks_database() -> None:
    def override_db() -> Generator[Session, None, None]:
        yield ReadySession()  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
