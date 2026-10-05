from __future__ import annotations

import json
import os
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from faultweaver.app import create_app
from faultweaver.config import Settings

EXPECTED_VERSION = "2026.4"
TERMINAL_STATES = {"Completed", "Failed", "Stopped"}


def _target_url() -> str:
    target = os.environ.get("FAULTWEAVER_WEBGOAT_URL")
    if not target:
        pytest.skip("set FAULTWEAVER_WEBGOAT_URL to run this external-lab test")
    parsed = urlsplit(target)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.path not in {"", "/"}
    ):
        pytest.fail("WebGoat compatibility tests require an HTTP loopback origin")
    return target.rstrip("/")


def _headers(headers: httpx.Headers) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in headers.multi_items()]


def _har_entry(response: httpx.Response) -> dict[str, object]:
    request = response.request
    request_content = request.content.decode("utf-8", errors="replace")
    request_data: dict[str, object] = {
        "method": request.method,
        "url": str(request.url),
        "httpVersion": "HTTP/1.1",
        "headers": _headers(request.headers),
        "queryString": [
            {"name": name, "value": value}
            for name, value in request.url.params.multi_items()
        ],
        "cookies": [],
        "headersSize": -1,
        "bodySize": len(request.content),
    }
    if request_content:
        request_data["postData"] = {
            "mimeType": request.headers.get("content-type", "application/octet-stream"),
            "text": request_content,
        }
    return {
        "startedDateTime": datetime.now(UTC).isoformat(),
        "time": 0,
        "request": request_data,
        "response": {
            "status": response.status_code,
            "statusText": response.reason_phrase,
            "httpVersion": "HTTP/1.1",
            "headers": _headers(response.headers),
            "cookies": [],
            "content": {
                "size": len(response.content),
                "mimeType": response.headers.get(
                    "content-type", "application/octet-stream"
                ),
                "text": response.text,
            },
            "redirectURL": response.headers.get("location", ""),
            "headersSize": -1,
            "bodySize": len(response.content),
        },
        "cache": {},
        "timings": {"send": -1, "wait": -1, "receive": -1},
    }


def _har_document(responses: list[httpx.Response]) -> str:
    return json.dumps(
        {
            "log": {
                "version": "1.2",
                "creator": {"name": "Faultweaver compatibility test", "version": "1"},
                "entries": [_har_entry(response) for response in responses],
            }
        }
    )


def _session_cookie(target: httpx.Client) -> list[dict[str, str]]:
    cookies = [
        {"name": item.name, "value": item.value}
        for item in target.cookies.jar
        if item.name == "JSESSIONID"
    ]
    assert len(cookies) == 1
    return cookies


def _cookie_header(cookies: list[dict[str, str]]) -> str:
    return "; ".join(f"{item['name']}={item['value']}" for item in cookies)


def _register(
    target: httpx.Client, label: str
) -> tuple[
    str,
    str,
    list[dict[str, str]],
    httpx.Response,
    httpx.Response,
    httpx.Response,
    httpx.Response,
]:
    username = f"c{label}{secrets.token_hex(4)}"
    password = f"s{secrets.token_hex(4)}9"
    registration = target.get("/WebGoat/registration")
    registration.raise_for_status()
    assert 'action="/WebGoat/register.mvc"' in registration.text
    registered = target.post(
        "/WebGoat/register.mvc",
        data={
            "username": username,
            "password": password,
            "matchingPassword": password,
            "agree": "agree",
        },
    )
    assert registered.status_code == 302
    assert "/WebGoat/attack?username=" in registered.headers["location"]
    start = target.get("/WebGoat/start.mvc")
    start.raise_for_status()
    assert "WebGoat" in start.text
    menu = target.get("/WebGoat/service/lessonmenu.mvc")
    menu.raise_for_status()
    assert isinstance(menu.json(), list)
    return (
        username,
        password,
        _session_cookie(target),
        registration,
        registered,
        start,
        menu,
    )


def _wait_for_run(client: TestClient, engagement_id: str, run_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/engagements/{engagement_id}/assessments/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] in TERMINAL_STATES:
            return run
        time.sleep(0.1)
    pytest.fail("WebGoat baseline assessment did not finish within 30 seconds")


def _import_curl(client: TestClient, engagement_id: str, command: str) -> str:
    preview = client.post(
        f"/api/engagements/{engagement_id}/imports/curl/preview",
        json={"content": command},
    )
    assert preview.status_code == 200
    assert preview.json()["accepted_count"] == 1
    imported = client.post(
        f"/api/engagements/{engagement_id}/imports/curl",
        json={"content": command, "filename": "browser-copy.txt"},
    )
    assert imported.status_code == 201
    return imported.json()["request_ids"][0]


def _create_identity(
    client: TestClient, engagement_id: str, name: str, cookies: list[dict[str, str]]
) -> str:
    response = client.post(
        f"/api/engagements/{engagement_id}/identities",
        json={"name": name, "cookies": cookies},
    )
    assert response.status_code == 201
    assert all(item["value"] == "[REDACTED]" for item in response.json()["cookies"])
    return response.json()["id"]


def test_real_webgoat_workflow(tmp_path: Path) -> None:
    base_url = _target_url()
    parsed_target = urlsplit(base_url)
    with httpx.Client(base_url=base_url, follow_redirects=False, timeout=20) as target:
        login_page = target.get("/WebGoat/login")
        login_page.raise_for_status()
        assert "WebGoat" in login_page.text
        assert 'action="/WebGoat/login"' in login_page.text
        (
            har_username,
            har_password,
            har_cookies,
            registration,
            registered,
            start,
            menu,
        ) = _register(target, "har")
        har = _har_document([login_page, registration, registered, start, menu])

    with httpx.Client(
        base_url=base_url, follow_redirects=False, timeout=20
    ) as session_a:
        _username_a, password_a, cookies_a, _, _, _, menu_a = _register(session_a, "a")

    with httpx.Client(
        base_url=base_url, follow_redirects=False, timeout=20
    ) as session_b:
        username_b, password_b, cookies_b, _, _, _, menu_b = _register(session_b, "b")

    assert menu_a.status_code == menu_b.status_code == 200
    passwords = {har_password, password_a, password_b}
    cookie_values = {item["value"] for item in har_cookies + cookies_a + cookies_b}

    database_url = f"sqlite:///{tmp_path / 'webgoat-compat.db'}"
    settings = Settings(
        database_url=database_url, allowed_origins=("http://localhost:5173",)
    )

    with TestClient(create_app(settings)) as client:
        engagement = client.post(
            "/api/engagements",
            json={
                "name": "OWASP WebGoat compatibility",
                "description": "Authorized loopback-only session workflow validation",
            },
        )
        assert engagement.status_code == 201
        engagement_id = engagement.json()["id"]
        scope = client.post(
            f"/api/engagements/{engagement_id}/scopes",
            json={
                "scheme": parsed_target.scheme,
                "hostname": parsed_target.hostname,
                "port": parsed_target.port or 80,
                "path_prefix": "/WebGoat/",
            },
        )
        assert scope.status_code == 201

        started = client.post(
            f"/api/engagements/{engagement_id}/assessments",
            json={
                "target_url": f"{base_url}/WebGoat/login",
                "max_pages": 4,
                "max_depth": 2,
                "max_requests": 8,
                "requests_per_second": 8,
                "concurrency": 2,
                "max_query_variants_per_path": 2,
                "inspect_site_metadata": False,
            },
        )
        assert started.status_code == 201
        run = _wait_for_run(client, engagement_id, started.json()["id"])
        assert run["status"] == "Completed"
        assert 1 <= run["request_count"] <= 8
        assert run["forms"]
        form_actions = {form["action_url"] for form in run["forms"]}
        assert f"{base_url}/WebGoat/login" in form_actions
        assert f"{base_url}/WebGoat/register.mvc" in form_actions
        assert all(form["method"] == "POST" for form in run["forms"])
        assert {"username", "password"}.issubset(
            {field["name"] for form in run["forms"] for field in form["fields"]}
        )
        crawler_requests = client.get(
            f"/api/engagements/{engagement_id}/requests?source=crawler"
        ).json()
        assert crawler_requests["total"] == run["request_count"]
        assert all(item["method"] == "GET" for item in crawler_requests["items"])
        assert all(
            client.get(f"/api/requests/{item['id']}").json()["request_body"] is None
            for item in crawler_requests["items"]
        )

        har_preview = client.post(
            f"/api/engagements/{engagement_id}/imports/har/preview",
            json={"content": har, "filename": "webgoat-browser.har"},
        )
        assert har_preview.status_code == 200
        assert har_preview.json()["accepted_count"] == 5
        assert har_preview.json()["response_count"] == 5
        assert not any(password in har_preview.text for password in passwords)
        har_import = client.post(
            f"/api/engagements/{engagement_id}/imports/har",
            json={"content": har, "filename": "webgoat-browser.har"},
        )
        assert har_import.status_code == 201
        assert har_import.json()["batch"]["display_id"] == "IMP-001"

        curl_get = (
            f"curl '{base_url}/WebGoat/service/lessonmenu.mvc' "
            f"--cookie '{_cookie_header(cookies_a)}' -H 'Accept: application/json'"
        )
        get_request_id = _import_curl(client, engagement_id, curl_get)
        post_body = urlencode({"username": username_b, "password": password_b})
        curl_post = (
            f"curl '{base_url}/WebGoat/login' --request POST "
            "-H 'Content-Type: application/x-www-form-urlencoded' "
            f"--data-raw '{post_body}'"
        )
        post_request_id = _import_curl(client, engagement_id, curl_post)
        batches = client.get(f"/api/engagements/{engagement_id}/imports").json()
        assert [item["display_id"] for item in batches] == [
            "IMP-003",
            "IMP-002",
            "IMP-001",
        ]

        registration_requests = client.get(
            f"/api/engagements/{engagement_id}/requests?q=register.mvc&source=har"
        ).json()["items"]
        imported_registration = next(
            item for item in registration_requests if item["method"] == "POST"
        )
        imported_registration = client.get(
            f"/api/requests/{imported_registration['id']}"
        ).json()
        assert har_username in imported_registration["request_body"]
        assert "password=[REDACTED]" in imported_registration["request_body"]
        assert "matchingPassword=[REDACTED]" in imported_registration["request_body"]
        assert har_password not in json.dumps(imported_registration)

        get_detail = client.get(f"/api/requests/{get_request_id}").json()
        assert any(
            item["name"].lower() == "cookie" and item["value"] == "[REDACTED]"
            for item in get_detail["request_headers"]
        )
        post_detail = client.get(f"/api/requests/{post_request_id}").json()
        assert post_detail["method"] == "POST"
        assert post_detail["request_body"] == (
            f"username={username_b}&password=[REDACTED]"
        )
        assert any(
            item["name"].lower() == "content-type"
            and item["value"] == "application/x-www-form-urlencoded"
            for item in post_detail["request_headers"]
        )

        surface = client.get(f"/api/engagements/{engagement_id}/attack-surface").json()
        menu_surface = next(
            item
            for item in surface
            if item["path_template"] == "/WebGoat/service/lessonmenu.mvc"
            and item["method"] == "GET"
        )
        assert set(menu_surface["sources"]) == {"curl", "har"}
        explorer = client.get(
            f"/api/engagements/{engagement_id}/requests?q=lessonmenu"
        ).json()
        assert explorer["total"] >= 2

        identity_a = _create_identity(client, engagement_id, "user-a", cookies_a)
        identity_b = _create_identity(client, engagement_id, "user-b", cookies_b)
        identities = client.get(f"/api/engagements/{engagement_id}/identities").json()
        anonymous = next(item for item in identities if item["is_anonymous"])
        assert {item["name"] for item in identities} == {
            "Anonymous",
            "user-a",
            "user-b",
        }
        assert not any(value in json.dumps(identities) for value in cookie_values)

        replay_b = client.post(
            f"/api/requests/{get_request_id}/replay",
            json={"identity_id": identity_b},
        )
        assert replay_b.status_code == 201
        assert replay_b.json()["response_status"] == 200
        assert replay_b.json()["auth_source"] == "identity"
        assert replay_b.json()["method"] == "GET"
        assert isinstance(json.loads(replay_b.json()["response_body"]), list)

        comparison = client.post(
            f"/api/requests/{get_request_id}/compare",
            json={
                "identity_a_id": identity_a,
                "identity_b_id": anonymous["id"],
            },
        )
        assert comparison.status_code == 201
        comparison_body = comparison.json()
        assert comparison_body["replay_a"]["response_status"] == 200
        assert comparison_body["replay_b"]["response_status"] == 200
        assert comparison_body["result"]["diff"]["json"]["present_a"] is True
        assert comparison_body["result"]["diff"]["json"]["present_b"] is False
        assert comparison_body["result"]["diff"]["normalized_similarity"] < 0.95
        assert comparison_body["result"]["diff"]["redirects"]["changed"] is True
        assert comparison_body["candidate"] is None
        comparison_id = comparison_body["id"]

        matrix = client.get(
            f"/api/engagements/{engagement_id}/authorization-matrix"
        ).json()
        row = next(
            item
            for item in matrix["rows"]
            if item["original_request_id"] == get_request_id
        )
        assert row["cells"][identity_a]["status"] == 200
        assert row["cells"][identity_b]["status"] == 200
        assert row["cells"][anonymous["id"]]["status"] == 200

        comparison_evidence = client.post(
            f"/api/engagements/{engagement_id}/evidence",
            json={
                "evidence_type": "Response Comparison",
                "title": "Authenticated JSON and anonymous HTML comparison",
                "source_comparison_id": comparison_id,
            },
        )
        assert comparison_evidence.status_code == 201
        assert comparison_evidence.json()["display_id"] == "EV-001"

        candidates = client.get(f"/api/engagements/{engagement_id}/candidates").json()
        baseline_candidate = next(
            item
            for item in candidates
            if item["assessment_run_id"] == run["id"]
            and item["title"] == "Content Security Policy is absent"
        )
        review = client.post(
            f"/api/engagements/{engagement_id}/candidates/{baseline_candidate['id']}/review",
            json={
                "decision": "Accepted",
                "note": "Confirmed from the captured login response",
            },
        )
        assert review.status_code == 200
        finding = client.post(
            f"/api/engagements/{engagement_id}/candidates/{baseline_candidate['id']}/promote",
            json={
                "title": "Content Security Policy header is absent",
                "category": "Security Misconfiguration",
                "severity": "Low",
                "affected_asset": parsed_target.netloc,
                "affected_endpoints": ["/WebGoat/login"],
                "description": "The observed login response omits Content-Security-Policy.",
                "impact": "The browser has fewer defense-in-depth controls.",
                "reproduction_steps": [
                    "Request the login page and inspect its headers."
                ],
                "remediation": "Define, test, and enforce a restrictive policy.",
                "references": ["https://owasp.org/www-project-secure-headers/"],
            },
        )
        assert finding.status_code == 201
        assert finding.json()["display_id"] == "FW-001"
        finding_id = finding.json()["id"]
        finding_evidence = client.post(
            f"/api/engagements/{engagement_id}/evidence",
            json={
                "evidence_type": "HTTP Request/Response",
                "title": "Login response without CSP",
                "source_exchange_id": baseline_candidate["original_exchange_id"],
                "finding_id": finding_id,
            },
        )
        assert finding_evidence.status_code == 201
        assert finding_evidence.json()["display_id"] == "EV-002"
        evidence_id = finding_evidence.json()["id"]
        evidence_snapshot = finding_evidence.json()["snapshot"]

    with TestClient(create_app(settings)) as restarted:
        persisted_batches = restarted.get(f"/api/engagements/{engagement_id}/imports")
        persisted_run = restarted.get(
            f"/api/engagements/{engagement_id}/assessments/{run['id']}"
        )
        persisted_comparison = restarted.get(f"/api/comparisons/{comparison_id}")
        persisted_finding = restarted.get(
            f"/api/engagements/{engagement_id}/findings/{finding_id}"
        )
        persisted_evidence = restarted.get(
            f"/api/engagements/{engagement_id}/evidence/{evidence_id}"
        )
        persisted_chains = restarted.get(
            f"/api/engagements/{engagement_id}/attack-chains"
        )

    assert [item["display_id"] for item in persisted_batches.json()] == [
        "IMP-003",
        "IMP-002",
        "IMP-001",
    ]
    assert persisted_run.json()["status"] == "Completed"
    assert persisted_comparison.status_code == 200
    assert persisted_finding.json()["display_id"] == "FW-001"
    assert persisted_evidence.json()["snapshot"] == evidence_snapshot
    assert persisted_chains.json() == []
    persisted_text = "\n".join(
        response.text
        for response in (
            persisted_batches,
            persisted_run,
            persisted_comparison,
            persisted_finding,
            persisted_evidence,
            persisted_chains,
        )
    )
    assert not any(password in persisted_text for password in passwords)
    assert not any(value in persisted_text for value in cookie_values)
