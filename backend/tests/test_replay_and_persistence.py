from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from tests.test_engagements_and_scope import create_engagement
from tests.test_http_import import authorize


def import_request(client: TestClient, engagement_id: str, path: str = "/api/projects") -> str:
    response = client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={
            "base_url": "http://app.test",
            "raw": f"GET {path} HTTP/1.1\r\nHost: app.test\r\nAccept: application/json\r\n\r\n",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_replay_stores_response_and_parent_link(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)
    request_id = import_request(app_client, engagement_id)

    response = app_client.post(f"/api/requests/{request_id}/replay", json={})

    assert response.status_code == 201
    replay = response.json()
    assert replay["source"] == "replay"
    assert replay["parent_exchange_id"] == request_id
    assert replay["response_status"] == 200
    assert replay["response_body"] == '{"ok":true,"path":"/api/projects"}'
    assert replay["response_elapsed_ms"] is not None
    assert replay["response_truncated"] is False


def test_redirect_is_checked_before_following(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    visited: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        visited.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://outside.test/private"})

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize(client, engagement_id)
        request_id = import_request(client, engagement_id, "/api/redirect")

        response = client.post(f"/api/requests/{request_id}/replay", json={})

    assert response.status_code == 403
    assert visited == ["http://app.test/api/redirect"]


def test_large_response_is_bounded(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1_000_100)

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize(client, engagement_id)
        request_id = import_request(client, engagement_id)

        response = client.post(f"/api/requests/{request_id}/replay", json={})

    assert response.status_code == 201
    assert len(response.json()["response_body"]) == 1_000_000
    assert response.json()["response_truncated"] is True


def test_database_state_survives_application_restart(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    with make_client() as first_client:
        engagement_id = create_engagement(first_client)
        authorize(first_client, engagement_id)
        request_id = import_request(first_client, engagement_id)

    with make_client() as second_client:
        engagement = second_client.get(f"/api/engagements/{engagement_id}")
        request = second_client.get(f"/api/requests/{request_id}")

    assert engagement.status_code == 200
    assert engagement.json()["request_count"] == 1
    assert request.status_code == 200
    assert request.json()["url"] == "http://app.test/api/projects"
