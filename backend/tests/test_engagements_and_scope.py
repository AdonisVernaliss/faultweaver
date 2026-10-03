from fastapi.testclient import TestClient

from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope


def create_engagement(client: TestClient) -> str:
    response = client.post(
        "/api/engagements",
        json={"name": "Synthetic tenant review", "description": "Authorized local target"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_engagement_and_scope(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)

    scope_response = app_client.post(
        f"/api/engagements/{engagement_id}/scopes",
        json={
            "scheme": "HTTP",
            "hostname": "LOCALHOST.",
            "port": 8080,
            "path_prefix": "/api/tenant",
        },
    )

    assert scope_response.status_code == 201
    assert scope_response.json() | {"id": "ignored", "engagement_id": "ignored"} == {
        "id": "ignored",
        "engagement_id": "ignored",
        "scheme": "http",
        "hostname": "localhost",
        "port": 8080,
        "path_prefix": "/api/tenant",
        "active": True,
    }

    detail = app_client.get(f"/api/engagements/{engagement_id}")
    assert detail.status_code == 200
    assert detail.json()["scope_count"] == 1
    assert detail.json()["request_count"] == 0


def test_scope_comparison_is_exact_and_path_aware() -> None:
    rule = ScopeRuleValue(
        scheme="https", hostname="example.test", port=443, path_prefix="/api/tenant"
    )

    assert is_url_in_scope("https://example.test/api/tenant", [rule])
    assert is_url_in_scope("https://example.test/api/tenant/orders?id=2", [rule])
    assert not is_url_in_scope("http://example.test/api/tenant", [rule])
    assert not is_url_in_scope("https://example.test:444/api/tenant", [rule])
    assert not is_url_in_scope("https://example.test.evil.test/api/tenant", [rule])
    assert not is_url_in_scope("https://example.test/api/tenant-admin", [rule])
    assert not is_url_in_scope("https://example.test/api/tenant/%2e%2e/admin", [rule])


def test_scope_rejects_invalid_rules(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)

    response = app_client.post(
        f"/api/engagements/{engagement_id}/scopes",
        json={
            "scheme": "file",
            "hostname": "localhost",
            "port": 8080,
            "path_prefix": "/",
        },
    )

    assert response.status_code == 422
