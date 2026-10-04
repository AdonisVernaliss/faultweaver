from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient


def _engagement(client: TestClient) -> str:
    engagement = client.post(
        "/api/engagements", json={"name": "Synthetic crawl", "description": ""}
    ).json()
    response = client.post(
        f"/api/engagements/{engagement['id']}/scopes",
        json={"scheme": "https", "hostname": "example.test", "port": 443, "path_prefix": "/"},
    )
    assert response.status_code == 201
    return engagement["id"]


def _wait_for(
    client: TestClient,
    engagement_id: str,
    run_id: str,
    predicate: Callable[[dict[str, object]], bool],
) -> dict[str, object]:
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        detail = client.get(f"/api/engagements/{engagement_id}/assessments/{run_id}").json()
        if predicate(detail):
            return detail
        time.sleep(0.01)
    raise AssertionError("assessment did not reach the expected state")


def test_assessment_crawls_only_scope_and_persists_analysis(make_client) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={
                    "content-type": "text/html",
                    "server": "Synthetic/1.2",
                    "set-cookie": "session=value; Path=/",
                },
                text=(
                    '<a href="/next">Next</a><a href="https://outside.test/nope">Outside</a>'
                    '<a href="/redirect">Redirect</a>'
                ),
            )
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "https://outside.test/landing"})
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"ok": True})

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = _engagement(client)
        response = client.post(
            f"/api/engagements/{engagement_id}/assessments",
            json={
                "target_url": "https://example.test/",
                "max_pages": 5,
                "max_depth": 2,
                "max_requests": 8,
                "requests_per_second": 20,
                "concurrency": 2,
                "inspect_site_metadata": False,
            },
        )
        assert response.status_code == 201
        run = response.json()
        assert run["display_id"] == "RUN-001"
        detail = _wait_for(
            client,
            engagement_id,
            run["id"],
            lambda item: item["status"] in {"Completed", "Failed"},
        )

        assert detail["status"] == "Completed"
        assert detail["request_count"] == 3
        assert detail["candidate_count"] >= 1
        assert detail["observation_count"] >= detail["candidate_count"]
        assert any(item["state"] == "skipped" for item in detail["discoveries"])
        assert all("outside.test" not in url for url in requested)
        assert "https://example.test/" in requested
        assert "https://example.test/next" in requested
        assert "https://example.test/redirect" in requested

        requests = client.get(f"/api/engagements/{engagement_id}/requests?source=crawler").json()
        assert requests["total"] == 3
        assert all(item["assessment_run_id"] == run["id"] for item in requests["items"])
        candidates = client.get(f"/api/engagements/{engagement_id}/candidates").json()
        assert any(item["assessment_run_id"] == run["id"] for item in candidates)
        surface = client.get(f"/api/engagements/{engagement_id}/attack-surface").json()
        assert any("crawler" in item["sources"] for item in surface)


def test_assessment_stop_is_graceful_and_preserves_partial_data(make_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        time.sleep(0.08)
        links = "".join(f'<a href="/page-{index}">p</a>' for index in range(20))
        return httpx.Response(200, headers={"content-type": "text/html"}, text=links)

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = _engagement(client)
        run = client.post(
            f"/api/engagements/{engagement_id}/assessments",
            json={
                "target_url": "https://example.test/",
                "max_pages": 50,
                "max_depth": 3,
                "max_requests": 50,
                "requests_per_second": 20,
                "concurrency": 1,
                "inspect_site_metadata": False,
            },
        ).json()
        stopped = client.post(f"/api/engagements/{engagement_id}/assessments/{run['id']}/stop")
        assert stopped.status_code == 202
        detail = _wait_for(
            client,
            engagement_id,
            run["id"],
            lambda item: item["status"] == "Stopped",
        )
        assert detail["stop_reason"] == "Stopped by operator"
        assert detail["request_count"] <= 1


def test_assessment_rejects_target_outside_exact_scope(app_client: TestClient) -> None:
    engagement_id = _engagement(app_client)
    response = app_client.post(
        f"/api/engagements/{engagement_id}/assessments",
        json={"target_url": "https://outside.test/"},
    )
    assert response.status_code == 403
