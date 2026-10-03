from collections.abc import Callable, Generator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from faultweaver.app import create_app
from faultweaver.config import Settings


@pytest.fixture
def app_client(tmp_path: Path) -> Generator[TestClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "x-demo": "synthetic"},
            json={"ok": True, "path": request.url.path},
        )

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'faultweaver.db'}",
        allowed_origins=("http://localhost:5173",),
    )
    with TestClient(create_app(settings, http_transport=httpx.MockTransport(handler))) as client:
        yield client


@pytest.fixture
def make_client(tmp_path: Path) -> Callable[[httpx.MockTransport | None], TestClient]:
    database_url = f"sqlite:///{tmp_path / 'shared.db'}"

    def factory(transport: httpx.MockTransport | None = None) -> TestClient:
        settings = Settings(
            database_url=database_url,
            allowed_origins=("http://localhost:5173",),
        )
        return TestClient(create_app(settings, http_transport=transport))

    return factory
