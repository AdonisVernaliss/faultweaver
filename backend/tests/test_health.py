from pathlib import Path

from fastapi.testclient import TestClient

from faultweaver.app import create_app
from faultweaver.config import Settings


def test_health_endpoint(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        allowed_origins=("http://localhost:5173",),
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
