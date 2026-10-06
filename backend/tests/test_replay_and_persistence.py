from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from faultweaver.http_traffic.models import HttpExchange
from faultweaver.redaction import REDACTED
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


def test_identity_replay_replaces_auth_and_preserves_the_original(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "set-cookie": "sid=response-secret"},
            json={"ok": True, "access_token": "response-token-secret"},
        )

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize(client, engagement_id)
        imported = client.post(
            f"/api/engagements/{engagement_id}/traffic/raw",
            json={
                "base_url": "http://app.test",
                "raw": (
                    "POST /api/projects/17 HTTP/1.1\r\n"
                    "Host: app.test\r\n"
                    "Authorization: Bearer original-secret\r\n"
                    "X-Tenant: original-tenant\r\n\r\n"
                    '{"operation":"read"}'
                ),
            },
        ).json()
        identity = client.post(
            f"/api/engagements/{engagement_id}/identities",
            json={
                "name": "Tenant B",
                "bearer_token": "selected-bearer-secret",
                "api_key_header": "X-API-Key",
                "api_key_value": "selected-api-secret",
                "cookies": [{"name": "sid", "value": "selected-cookie-secret"}],
                "custom_headers": [{"name": "X-Tenant", "value": "tenant-b"}],
            },
        ).json()

        response = client.post(
            f"/api/requests/{imported['id']}/replay",
            json={
                "identity_id": identity["id"],
                "headers": [
                    {"name": "Accept", "value": "application/json"},
                    {"name": "Authorization", "value": "Bearer operator-secret"},
                    {"name": "X-Tenant", "value": "operator-tenant"},
                ],
            },
        )

        assert response.status_code == 201
        replay = response.json()
        assert replay["identity_id"] == identity["id"]
        assert replay["auth_source"] == "identity"
        assert replay["operator_modified"] is True
        assert {item["name"].lower(): item["value"] for item in replay["request_headers"]} == {
            "accept": "application/json",
            "authorization": REDACTED,
            "x-api-key": REDACTED,
            "cookie": REDACTED,
            "x-tenant": REDACTED,
        }
        assert {item["name"].lower(): item["value"] for item in replay["response_headers"]}[
            "set-cookie"
        ] == REDACTED
        assert replay["response_body"] == '{"ok":true,"access_token":"[REDACTED]"}'

        sent = captured[0]
        assert sent.headers["authorization"] == "Bearer selected-bearer-secret"
        assert sent.headers["x-api-key"] == "selected-api-secret"
        assert sent.headers["cookie"] == "sid=selected-cookie-secret"
        assert sent.headers["x-tenant"] == "tenant-b"

        with client.app.state.session_factory() as session:
            original = session.get(HttpExchange, imported["id"])
            stored_replay = session.scalar(
                select(HttpExchange).where(HttpExchange.parent_exchange_id == imported["id"])
            )
            assert original is not None and stored_replay is not None
            assert (
                next(
                    item["value"]
                    for item in original.request_headers
                    if item["name"].lower() == "authorization"
                )
                == "Bearer original-secret"
            )
            assert (
                next(
                    item["value"]
                    for item in stored_replay.request_headers
                    if item["name"].lower() == "authorization"
                )
                == "Bearer selected-bearer-secret"
            )


def test_anonymous_identity_removes_known_auth_headers(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(401, json={"detail": "authentication required"})

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize(client, engagement_id)
        request_id = import_request(client, engagement_id, "/api/projects/17")
        client.post(
            f"/api/engagements/{engagement_id}/identities",
            json={
                "name": "Tenant context",
                "custom_headers": [{"name": "X-Tenant", "value": "tenant-a"}],
            },
        )
        anonymous = next(
            item
            for item in client.get(f"/api/engagements/{engagement_id}/identities").json()
            if item["is_anonymous"]
        )

        response = client.post(
            f"/api/requests/{request_id}/replay",
            json={
                "identity_id": anonymous["id"],
                "headers": [
                    {"name": "Accept", "value": "application/json"},
                    {"name": "Authorization", "value": "Bearer original"},
                    {"name": "X-Tenant", "value": "tenant-a"},
                ],
            },
        )

    assert response.status_code == 201
    sent_headers = {name.lower(): value for name, value in captured[0].headers.multi_items()}
    assert "authorization" not in sent_headers
    assert "x-tenant" not in sent_headers
    assert sent_headers["accept"] == "application/json"
