import json
from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tests.test_engagements_and_scope import create_engagement


def authorize_example(client: TestClient, engagement_id: str) -> None:
    response = client.post(
        f"/api/engagements/{engagement_id}/scopes",
        json={
            "scheme": "https",
            "hostname": "api.example.test",
            "port": 443,
            "path_prefix": "/api",
        },
    )
    assert response.status_code == 201


def sample_har(*, include_invalid: bool = False) -> str:
    entries: list[object] = [
        {
            "startedDateTime": "2026-01-02T03:04:05Z",
            "time": 18.5,
            "request": {
                "method": "GET",
                "url": (
                    "https://api.example.test/api/users/17"
                    "?full=true&token=synthetic-query-secret"
                ),
                "headers": [
                    {"name": "Authorization", "value": "Bearer synthetic-har-secret"},
                    {"name": "X-Trace", "value": "one"},
                    {"name": "X-Trace", "value": "two"},
                ],
            },
            "response": {
                "status": 200,
                "headers": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Set-Cookie", "value": "sid=synthetic-response-secret"},
                ],
                "content": {
                    "mimeType": "application/json",
                    "text": '{"id":17,"access_token":"synthetic-body-secret"}',
                },
            },
        }
    ]
    if include_invalid:
        entries.extend(
            [
                {"request": {"method": "GET"}},
                {
                    "request": {
                        "method": "GET",
                        "url": "https://outside.example.test/api/ignored",
                    }
                },
            ]
        )
    return json.dumps({"log": {"version": "1.2", "entries": entries}})


def sample_openapi() -> str:
    return json.dumps(
        {
            "openapi": "3.1.0",
            "servers": [{"url": "https://api.example.test"}],
            "paths": {
                "/api/users/{id}": {
                    "get": {
                        "operationId": "getUser",
                        "tags": ["Users"],
                        "security": [{"bearerAuth": []}],
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {"200": {"description": "User"}},
                    }
                },
                "/api/admin": {
                    "post": {
                        "requestBody": {"$ref": "#/components/requestBodies/AdminBody"},
                        "responses": {"204": {"description": "Updated"}},
                    }
                },
            },
            "components": {
                "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
                "requestBodies": {
                    "AdminBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"enabled": {"type": "boolean"}},
                                }
                            }
                        }
                    }
                },
            },
        }
    )


def test_har_import_redaction_partial_failure_and_deduplication(
    app_client: TestClient,
) -> None:
    engagement_id = create_engagement(app_client)
    authorize_example(app_client, engagement_id)
    har = sample_har(include_invalid=True)

    preview = app_client.post(
        f"/api/engagements/{engagement_id}/imports/har/preview",
        json={"content": har, "filename": "captures/sample.har"},
    )
    imported = app_client.post(
        f"/api/engagements/{engagement_id}/imports/har",
        json={"content": har, "filename": "captures/sample.har"},
    )

    assert preview.status_code == 200
    assert preview.json()["accepted_count"] == 1
    assert preview.json()["skipped_count"] == 2
    assert "synthetic-har-secret" not in preview.text
    assert "synthetic-query-secret" not in preview.text
    assert imported.status_code == 201
    batch = imported.json()["batch"]
    assert batch["display_id"] == "IMP-001"
    assert batch["status"] == "partial"
    assert batch["original_filename"] == "sample.har"
    assert batch["imported_count"] == 1
    assert batch["response_count"] == 1
    assert batch["skipped_count"] == 2

    request_id = imported.json()["request_ids"][0]
    detail = app_client.get(f"/api/requests/{request_id}")
    assert detail.status_code == 200
    assert detail.json()["source"] == "har"
    assert detail.json()["import_batch_id"] == batch["id"]
    assert "synthetic-har-secret" not in detail.text
    assert "synthetic-response-secret" not in detail.text
    assert "synthetic-body-secret" not in detail.text
    assert "synthetic-query-secret" not in detail.text
    assert "[REDACTED]" in detail.text

    duplicate = app_client.post(
        f"/api/engagements/{engagement_id}/imports/har",
        json={"content": har, "filename": "renamed.har"},
    )
    surface = app_client.get(f"/api/engagements/{engagement_id}/attack-surface").json()
    requests = app_client.get(
        f"/api/engagements/{engagement_id}/requests", params={"source": "har"}
    ).json()

    assert duplicate.json()["batch"]["display_id"] == "IMP-002"
    assert any(
        "Probable duplicate of IMP-001" in item for item in duplicate.json()["batch"]["warnings"]
    )
    assert len(surface) == 1
    assert surface[0]["state"] == "observed_only"
    assert surface[0]["observed_request_count"] == 2
    assert requests["total"] == 2


def test_curl_preview_import_and_shell_injection_remain_inert(
    app_client: TestClient, tmp_path: Path
) -> None:
    engagement_id = create_engagement(app_client)
    authorize_example(app_client, engagement_id)
    command = (
        "curl 'https://api.example.test/api/orders/17?full=true' "
        "-H 'Authorization: Bearer synthetic-curl-secret' "
        "-H 'Content-Type: application/json' --data-raw '{\"state\":\"open\"}'"
    )

    preview = app_client.post(
        f"/api/engagements/{engagement_id}/imports/curl/preview", json={"content": command}
    )
    imported = app_client.post(
        f"/api/engagements/{engagement_id}/imports/curl", json={"content": command}
    )

    assert preview.status_code == 200
    assert preview.json()["requests"][0] | {"url": "ignored"} == {
        "source_entry_index": 0,
        "method": "POST",
        "url": "ignored",
        "header_count": 2,
        "cookie_count": 0,
        "body_kind": "application/json",
        "body_bytes": 16,
        "response_status": None,
        "scope_allowed": True,
    }
    assert "synthetic-curl-secret" not in preview.text
    assert imported.status_code == 201
    request_detail = app_client.get(f"/api/requests/{imported.json()['request_ids'][0]}")
    assert request_detail.json()["source"] == "curl"
    assert "synthetic-curl-secret" not in request_detail.text

    marker = tmp_path / "must-not-exist"
    malicious = f"curl 'https://api.example.test/api/17/$(touch {marker})'"
    rejected = app_client.post(
        f"/api/engagements/{engagement_id}/imports/curl/preview",
        json={"content": malicious},
    )
    assert rejected.status_code == 422
    assert not marker.exists()


def test_openapi_enriches_observed_surface_and_is_engagement_scoped(
    app_client: TestClient,
) -> None:
    engagement_id = create_engagement(app_client)
    other_engagement = create_engagement(app_client)
    authorize_example(app_client, engagement_id)
    observed = app_client.post(
        f"/api/engagements/{engagement_id}/imports/har",
        json={"content": sample_har()},
    )
    assert observed.status_code == 201

    preview = app_client.post(
        f"/api/engagements/{engagement_id}/imports/openapi/preview",
        json={"content": sample_openapi(), "filename": "api.yaml"},
    )
    imported = app_client.post(
        f"/api/engagements/{engagement_id}/imports/openapi",
        json={"content": sample_openapi(), "filename": "api.yaml"},
    )

    assert preview.status_code == 200
    assert preview.json()["accepted_count"] == 2
    assert {item["path_template"] for item in preview.json()["endpoints"]} == {
        "/api/users/{id}",
        "/api/admin",
    }
    assert imported.status_code == 201
    assert imported.json()["batch"]["display_id"] == "IMP-002"
    assert imported.json()["batch"]["imported_count"] == 2
    surface = app_client.get(f"/api/engagements/{engagement_id}/attack-surface").json()
    by_path = {item["path_template"]: item for item in surface}
    assert by_path["/api/users/{id}"]["state"] == "observed_and_declared"
    assert by_path["/api/users/{id}"]["sources"] == ["openapi", "har"]
    assert by_path["/api/users/{id}"]["observed_request_count"] == 1
    assert by_path["/api/users/{id}"]["metadata"]["operation_id"] == "getUser"
    assert by_path["/api/admin"]["state"] == "declared_only"
    assert app_client.get(f"/api/engagements/{other_engagement}/attack-surface").json() == []
    other_batches = app_client.get(f"/api/engagements/{other_engagement}/imports").json()
    assert other_batches == []


def test_har_curl_and_openapi_survive_restart_without_openapi_network_calls(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    visited: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        visited.append(str(request.url))
        return httpx.Response(500)

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize_example(client, engagement_id)
        assert (
            client.post(
                f"/api/engagements/{engagement_id}/imports/har",
                json={"content": sample_har()},
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/engagements/{engagement_id}/imports/curl",
                json={"content": "curl https://api.example.test/api/orders/17"},
            ).status_code
            == 201
        )
        external_ref_document = json.loads(sample_openapi())
        external_ref_document["paths"]["/api/external"] = {
            "$ref": "https://untrusted.example.test/path-item.json"
        }
        assert (
            client.post(
                f"/api/engagements/{engagement_id}/imports/openapi",
                json={"content": json.dumps(external_ref_document)},
            ).status_code
            == 201
        )
        assert visited == []

    with make_client() as restarted:
        batches = restarted.get(f"/api/engagements/{engagement_id}/imports").json()
        requests = restarted.get(f"/api/engagements/{engagement_id}/requests").json()
        surface = restarted.get(f"/api/engagements/{engagement_id}/attack-surface").json()

    assert [item["display_id"] for item in batches] == ["IMP-003", "IMP-002", "IMP-001"]
    assert {item["source"] for item in requests["items"]} == {"har", "curl"}
    assert {item["state"] for item in surface} >= {"observed_only", "declared_only"}
