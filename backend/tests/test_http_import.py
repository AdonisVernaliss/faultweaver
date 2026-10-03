from fastapi.testclient import TestClient

from tests.test_engagements_and_scope import create_engagement


def authorize(client: TestClient, engagement_id: str) -> None:
    response = client.post(
        f"/api/engagements/{engagement_id}/scopes",
        json={"scheme": "http", "hostname": "app.test", "port": 80, "path_prefix": "/api"},
    )
    assert response.status_code == 201


def test_raw_http_import_and_request_listing(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)
    raw = (
        "POST /api/projects?state=open HTTP/1.1\r\n"
        "Host: app.test\r\n"
        "Content-Type: application/json\r\n"
        "X-Trace: first\r\n"
        "X-Trace: second\r\n\r\n"
        '{"name":"Synthetic"}'
    )

    response = app_client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={"base_url": "http://app.test", "raw": raw},
    )

    assert response.status_code == 201
    imported = response.json()
    assert imported["method"] == "POST"
    assert imported["url"] == "http://app.test/api/projects?state=open"
    assert imported["path"] == "/api/projects"
    assert imported["query"] == "state=open"
    assert imported["source"] == "raw_import"
    assert imported["request_body"] == '{"name":"Synthetic"}'
    assert [header for header in imported["request_headers"] if header["name"] == "X-Trace"] == [
        {"name": "X-Trace", "value": "first"},
        {"name": "X-Trace", "value": "second"},
    ]

    listing = app_client.get(f"/api/engagements/{engagement_id}/requests", params={"q": "projects"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == imported["id"]

    detail = app_client.get(f"/api/requests/{imported['id']}")
    assert detail.status_code == 200
    assert detail.json()["raw_request"].startswith("POST /api/projects?state=open HTTP/1.1")


def test_import_rejects_out_of_scope_and_malformed_requests(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)

    out_of_scope = app_client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={
            "base_url": "http://other.test",
            "raw": "GET /api/users HTTP/1.1\r\nHost: other.test\r\n\r\n",
        },
    )
    malformed = app_client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={"base_url": "http://app.test", "raw": "not-http"},
    )

    assert out_of_scope.status_code == 403
    assert malformed.status_code == 422
