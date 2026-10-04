from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from faultweaver.assessments.models import AssessmentRun


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
                    '<form action="/submit" method="post"><input name="password" '
                    'type="password"><input name="csrf" type="hidden" value="token"></form>'
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
        assert "https://example.test/submit" not in requested
        assert detail["forms"] == [
            {
                "id": detail["forms"][0]["id"],
                "exchange_id": detail["forms"][0]["exchange_id"],
                "action_url": "https://example.test/submit",
                "method": "POST",
                "enctype": "application/x-www-form-urlencoded",
                "fields": [
                    {
                        "name": "password",
                        "type": "password",
                        "hidden": False,
                        "has_value": False,
                    },
                    {"name": "csrf", "type": "hidden", "hidden": True, "has_value": True},
                ],
            }
        ]

        requests = client.get(f"/api/engagements/{engagement_id}/requests?source=crawler").json()
        assert requests["total"] == 3
        assert all(item["assessment_run_id"] == run["id"] for item in requests["items"])
        candidates = client.get(f"/api/engagements/{engagement_id}/candidates").json()
        candidate = next(
            item
            for item in candidates
            if item["assessment_run_id"] == run["id"]
            and item["check_id"] == "headers.content-security-policy"
        )
        assert candidate["check_id"] == "headers.content-security-policy"
        assert candidate["finding_id"] is None
        evidence = client.post(
            f"/api/engagements/{engagement_id}/evidence",
            json={
                "evidence_type": "HTTP Request/Response",
                "title": "Baseline supporting request",
                "source_exchange_id": candidate["original_exchange_id"],
                "source_candidate_id": candidate["id"],
            },
        )
        assert evidence.status_code == 201
        replay = client.post(f"/api/requests/{candidate['original_exchange_id']}/replay", json={})
        assert replay.status_code == 201
        review = client.post(
            f"/api/engagements/{engagement_id}/candidates/{candidate['id']}/review",
            json={"decision": "Accepted", "note": "Verified supporting response manually"},
        )
        assert review.status_code == 200
        finding = client.post(
            f"/api/engagements/{engagement_id}/candidates/{candidate['id']}/promote",
            json={
                "severity": "Low",
                "description": "Operator-authored verification result",
                "affected_endpoints": ["/"],
            },
        )
        assert finding.status_code == 201
        assert finding.json()["display_id"] == "FW-001"
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


def test_assessment_rejects_unboundedly_slow_rate(app_client: TestClient) -> None:
    engagement_id = _engagement(app_client)
    response = app_client.post(
        f"/api/engagements/{engagement_id}/assessments",
        json={"target_url": "https://example.test/", "requests_per_second": 0.09},
    )
    assert response.status_code == 422


def test_completed_run_survives_restart_and_stale_state_is_recovered(make_client) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"content-type": "application/json"}, json={})
    )
    with make_client(transport) as client:
        engagement_id = _engagement(client)
        run = client.post(
            f"/api/engagements/{engagement_id}/assessments",
            json={
                "target_url": "https://example.test/",
                "max_requests": 1,
                "requests_per_second": 20,
                "inspect_site_metadata": False,
            },
        ).json()
        detail = _wait_for(
            client,
            engagement_id,
            run["id"],
            lambda item: item["status"] == "Completed",
        )
        assert detail["request_count"] == 1
        with client.app.state.session_factory() as session:
            stored = session.get(AssessmentRun, run["id"])
            assert stored is not None
            stored.status = "Running"
            stored.finished_at = None
            session.commit()

    with make_client(transport) as restarted:
        recovered = restarted.get(
            f"/api/engagements/{engagement_id}/assessments/{run['id']}"
        ).json()
        assert recovered["status"] == "Stopped"
        assert recovered["stop_reason"] == "Interrupted by application restart"
        assert recovered["request_count"] == 1
        assert recovered["request_ids"]
