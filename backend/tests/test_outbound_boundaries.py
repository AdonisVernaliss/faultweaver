import httpx
import pytest

from faultweaver.http_traffic.replay import execute_replay
from faultweaver.http_traffic.schemas import HeaderEntry
from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope
from tests.test_engagements_and_scope import create_engagement
from tests.test_http_import import authorize
from tests.test_replay_and_persistence import import_request


def test_cross_origin_redirect_drops_all_identity_headers(make_client):
    visited = []

    def handler(request):
        visited.append(request)
        if len(visited) == 1:
            return httpx.Response(302, headers={"location": "http://app.test:8080/api/end"})
        return httpx.Response(200, text="ok")

    with make_client(httpx.MockTransport(handler)) as client:
        engagement = create_engagement(client)
        authorize(client, engagement)
        client.post(
            f"/api/engagements/{engagement}/scopes",
            json={"scheme": "http", "hostname": "app.test", "port": 8080},
        ).raise_for_status()
        identity = client.post(
            f"/api/engagements/{engagement}/identities",
            json={
                "name": "Redirect identity",
                "api_key_header": "X-Workspace",
                "api_key_value": "synthetic-workspace-secret",
                "custom_headers": [{"name": "X-Principal", "value": "synthetic-principal"}],
            },
        ).json()
        request_id = import_request(client, engagement)
        response = client.post(
            f"/api/requests/{request_id}/replay", json={"identity_id": identity["id"]}
        )
        assert response.status_code == 201
    assert visited[0].headers["x-workspace"] == "synthetic-workspace-secret"
    assert "x-workspace" not in visited[1].headers
    assert "x-principal" not in visited[1].headers


def test_cross_origin_redirect_cannot_reintroduce_cookie_or_api_key():
    visited = []

    def handler(request):
        visited.append(request)
        if len(visited) == 1:
            return httpx.Response(
                302,
                headers={
                    "location": "http://app.test:8080/end",
                    "set-cookie": "session=synthetic-redirect-cookie; Path=/",
                },
            )
        return httpx.Response(200, text="ok")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        execute_replay(
            client,
            method="GET",
            url="http://app.test/start",
            headers=[HeaderEntry(name="X-API-Key", value="synthetic-api-secret")],
            body=None,
            scopes=[ScopeRuleValue("http", "app.test", port) for port in (80, 8080)],
            max_redirects=2,
            max_response_bytes=1000,
        )
    assert "cookie" not in visited[1].headers
    assert "x-api-key" not in visited[1].headers


def test_scope_error_does_not_echo_redirect_secret(make_client):
    def handler(request):
        return httpx.Response(
            302, headers={"location": "http://outside.test/?token=synthetic-redirect-secret"}
        )

    with make_client(httpx.MockTransport(handler)) as client:
        engagement = create_engagement(client)
        authorize(client, engagement)
        request_id = import_request(client, engagement)
        response = client.post(f"/api/requests/{request_id}/replay", json={})
        assert response.status_code == 403
        assert "synthetic-redirect-secret" not in response.text


@pytest.mark.parametrize(
    "url",
    [
        "http://app.test:0/api",
        "http://app.test/api/%2525252e%2525252e/private",
        "http://app.test/\napi",
        "http://app.test.evil.test/api",
        "http://user:password@app.test/api",
        "https://app.test/api",
        "http://app.test/api/../private",
        "http://app.test/api/%2f../private",
    ],
)
def test_ambiguous_or_outside_urls_are_not_authorized(url):
    assert not is_url_in_scope(url, [ScopeRuleValue("http", "app.test", 80, "/api")])


def test_replay_captures_same_origin_redirect_cookie_in_provenance():
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(
                302, headers={"location": "/end", "set-cookie": "sid=synthetic-hop; Path=/"}
            )
        assert request.headers["cookie"] == "sid=synthetic-hop"
        return httpx.Response(200, text="ok")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute_replay(
            client,
            method="GET",
            url="http://app.test/start",
            headers=[],
            body=None,
            scopes=[ScopeRuleValue("http", "app.test", 80)],
            max_redirects=2,
            max_response_bytes=1000,
        )
    assert {h["name"].lower(): h["value"] for h in result.request_headers}[
        "cookie"
    ] == "sid=synthetic-hop"


def test_baseline_does_not_silently_acquire_authentication_cookies(app_client):
    from faultweaver.assessments.frontier import FrontierItem

    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html",
                "set-cookie": "sid=synthetic-auto-session; Path=/",
            },
            text="ok",
        )

    manager = app_client.app.state.assessment_manager
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        for path in ("/first", "/second"):
            url = "http://app.test" + path
            result = manager._fetch(
                client,
                FrontierItem(url, url, 0, "seed"),
                1000,
                [ScopeRuleValue("http", "app.test", 80)],
            )
            assert result.status == 200
    assert all("cookie" not in request.headers for request in captured)


def test_crawler_transport_error_does_not_echo_raw_url(app_client):
    from faultweaver.assessments.frontier import FrontierItem

    def handler(request):
        raise httpx.ConnectError("Failed https://app.test/?token=synthetic-error-secret")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = app_client.app.state.assessment_manager._fetch(
            client,
            FrontierItem("http://app.test/", "http://app.test/", 0, "seed"),
            1000,
            [ScopeRuleValue("http", "app.test", 80)],
        )
    assert result.error == "Request failed: ConnectError"
