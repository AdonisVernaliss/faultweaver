from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from faultweaver.app import create_app
from faultweaver.config import Settings

TERMINAL_STATES = {"Completed", "Failed", "Stopped"}


class _TokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "input" and values.get("name") == "user_token":
            self.token = values.get("value")


def _target_url() -> str:
    target = os.environ.get("FAULTWEAVER_DVWA_URL")
    if not target:
        pytest.skip("set FAULTWEAVER_DVWA_URL to run this external-lab test")
    parsed = urlsplit(target)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("DVWA compatibility tests require an HTTP loopback target")
    return target.rstrip("/")


def _credential(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} must be supplied by the compatibility runner")
    return value


def _token(response: httpx.Response) -> str:
    parser = _TokenParser()
    parser.feed(response.text)
    assert parser.token
    return parser.token


def _login(
    target: httpx.Client,
) -> tuple[httpx.Response, httpx.Response, httpx.Response]:
    login_page = target.get("/login.php")
    login_page.raise_for_status()
    login = target.post(
        "/login.php",
        data={
            "username": _credential("FAULTWEAVER_DVWA_USERNAME"),
            "password": _credential("FAULTWEAVER_DVWA_PASSWORD"),
            "Login": "Login",
            "user_token": _token(login_page),
        },
    )
    assert login.status_code == 302
    assert login.headers["location"].endswith("index.php")
    home = target.get(login.headers["location"])
    home.raise_for_status()
    assert "Welcome to Damn Vulnerable Web Application" in home.text
    return login_page, login, home


def _session_cookies(target: httpx.Client) -> list[dict[str, str]]:
    cookies = [
        {"name": item.name, "value": item.value}
        for item in target.cookies.jar
        if item.name in {"PHPSESSID", "security"}
    ]
    assert {item["name"] for item in cookies} == {"PHPSESSID", "security"}
    return cookies


def _cookie_header(cookies: list[dict[str, str]]) -> str:
    return "; ".join(f"{item['name']}={item['value']}" for item in cookies)


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


def _wait_for_run(client: TestClient, engagement_id: str, run_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/engagements/{engagement_id}/assessments/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] in TERMINAL_STATES:
            return run
        time.sleep(0.1)
    pytest.fail("DVWA baseline assessment did not finish within 30 seconds")


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


def test_real_dvwa_workflow(tmp_path: Path) -> None:
    base_url = _target_url()
    parsed_target = urlsplit(base_url)
    with httpx.Client(base_url=base_url, follow_redirects=False, timeout=15) as target:
        setup = target.get("/setup.php")
        setup.raise_for_status()
        assert "Damn Vulnerable Web Application (DVWA)" in setup.text
        assert "Database Setup" in setup.text

        login_page, login, home = _login(target)
        reflected_form = target.get("/vulnerabilities/xss_r/")
        reflected_form.raise_for_status()
        assert 'method="GET"' in reflected_form.text
        reflected_result = target.get(
            "/vulnerabilities/xss_r/",
            params={
                "name": "compatibility check",
                "Submit": "Submit",
                "user_token": _token(reflected_form),
            },
        )
        reflected_result.raise_for_status()
        assert "compatibility check" in reflected_result.text

        security_form = target.get("/security.php")
        security_form.raise_for_status()
        security_submit = target.post(
            "/security.php",
            data={
                "security": "impossible",
                "seclev_submit": "Submit",
                "user_token": _token(security_form),
            },
        )
        assert security_submit.status_code == 302
        authenticated_cookies = _session_cookies(target)

        har = _har_document(
            [
                login_page,
                login,
                home,
                reflected_form,
                reflected_result,
                security_form,
                security_submit,
            ]
        )

    with httpx.Client(
        base_url=base_url, follow_redirects=False, timeout=15
    ) as form_session:
        _login(form_session)
        replay_form = form_session.get("/security.php")
        replay_form.raise_for_status()
        replay_form_token = _token(replay_form)
        form_cookies = _session_cookies(form_session)

    with httpx.Client(
        base_url=base_url, follow_redirects=False, timeout=15
    ) as get_session:
        _login(get_session)
        replay_get = get_session.get("/vulnerabilities/xss_r/")
        replay_get.raise_for_status()
        replay_get_token = _token(replay_get)
        get_cookies = _session_cookies(get_session)

    database_url = f"sqlite:///{tmp_path / 'dvwa-compat.db'}"
    settings = Settings(
        database_url=database_url, allowed_origins=("http://localhost:5173",)
    )
    password = _credential("FAULTWEAVER_DVWA_PASSWORD")

    with TestClient(create_app(settings)) as client:
        engagement = client.post(
            "/api/engagements",
            json={
                "name": "DVWA compatibility",
                "description": "Authorized loopback-only classic form validation",
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
                "path_prefix": "/",
            },
        )
        assert scope.status_code == 201

        started = client.post(
            f"/api/engagements/{engagement_id}/assessments",
            json={
                "target_url": f"{base_url}/login.php",
                "max_pages": 10,
                "max_depth": 2,
                "max_requests": 12,
                "requests_per_second": 10,
                "concurrency": 2,
                "max_query_variants_per_path": 2,
                "inspect_site_metadata": False,
            },
        )
        assert started.status_code == 201
        run = _wait_for_run(client, engagement_id, started.json()["id"])
        assert run["status"] == "Completed"
        assert run["request_count"] >= 1
        assert run["forms"]
        assert all(form["method"] == "POST" for form in run["forms"])
        assert any(
            field["name"] == "user_token"
            and field["hidden"] is True
            and field["has_value"] is True
            for form in run["forms"]
            for field in form["fields"]
        )
        crawler_requests = client.get(
            f"/api/engagements/{engagement_id}/requests?source=crawler"
        ).json()
        assert crawler_requests["total"] == run["request_count"]
        assert all(item["method"] == "GET" for item in crawler_requests["items"])
        assert all(item["request_body"] is None for item in crawler_requests["items"])

        har_preview = client.post(
            f"/api/engagements/{engagement_id}/imports/har/preview",
            json={"content": har, "filename": "dvwa-browser.har"},
        )
        assert har_preview.status_code == 200
        assert har_preview.json()["accepted_count"] == 7
        assert har_preview.json()["response_count"] == 7
        assert password not in har_preview.text
        har_import = client.post(
            f"/api/engagements/{engagement_id}/imports/har",
            json={"content": har, "filename": "dvwa-browser.har"},
        )
        assert har_import.status_code == 201
        assert har_import.json()["batch"]["display_id"] == "IMP-001"

        get_query = urlencode(
            {
                "name": "compatibility check",
                "Submit": "Submit",
                "user_token": replay_get_token,
            }
        )
        curl_get = (
            f"curl '{base_url}/vulnerabilities/xss_r/?{get_query}' "
            f"--cookie '{_cookie_header(get_cookies)}' -H 'Accept: text/html'"
        )
        get_request_id = _import_curl(client, engagement_id, curl_get)

        post_body = urlencode(
            {
                "security": "impossible",
                "seclev_submit": "Submit",
                "user_token": replay_form_token,
            }
        )
        curl_post = (
            f"curl '{base_url}/security.php' --request POST "
            "-H 'Content-Type: application/x-www-form-urlencoded' "
            f"--cookie '{_cookie_header(form_cookies)}' --data-raw '{post_body}'"
        )
        post_request_id = _import_curl(client, engagement_id, curl_post)
        batches = client.get(f"/api/engagements/{engagement_id}/imports").json()
        assert [item["display_id"] for item in batches] == [
            "IMP-003",
            "IMP-002",
            "IMP-001",
        ]

        login_requests = client.get(
            f"/api/engagements/{engagement_id}/requests?q=login.php&source=har"
        ).json()["items"]
        imported_login = next(
            item for item in login_requests if item["method"] == "POST"
        )
        assert password not in json.dumps(imported_login)
        assert "password=[REDACTED]" in imported_login["request_body"]
        assert "user_token=[REDACTED]" in imported_login["request_body"]
        post_detail = client.get(f"/api/requests/{post_request_id}").json()
        assert post_detail["method"] == "POST"
        assert post_detail["request_body"].startswith("security=impossible&")
        assert "user_token=[REDACTED]" in post_detail["request_body"]
        assert any(
            item["name"].lower() == "content-type"
            and item["value"] == "application/x-www-form-urlencoded"
            for item in post_detail["request_headers"]
        )
        assert any(
            item["name"].lower() == "cookie" and item["value"] == "[REDACTED]"
            for item in post_detail["request_headers"]
        )

        surface = client.get(f"/api/engagements/{engagement_id}/attack-surface").json()
        reflected_surface = next(
            item
            for item in surface
            if item["path_template"] == "/vulnerabilities/xss_r/"
            and item["method"] == "GET"
        )
        security_surface = next(
            item
            for item in surface
            if item["path_template"] == "/security.php" and item["method"] == "POST"
        )
        assert set(reflected_surface["sources"]) == {"curl", "har"}
        assert set(security_surface["sources"]) == {"curl", "har"}
        explorer = client.get(
            f"/api/engagements/{engagement_id}/requests?q=xss_r"
        ).json()
        assert explorer["total"] >= 3

        identity_a = _create_identity(client, engagement_id, "user-a", get_cookies)
        form_identity = _create_identity(
            client, engagement_id, "form-session", form_cookies
        )
        identities = client.get(f"/api/engagements/{engagement_id}/identities").json()
        anonymous = next(item for item in identities if item["is_anonymous"])
        assert {item["name"] for item in identities} == {
            "Anonymous",
            "form-session",
            "user-a",
        }
        cookie_values = {
            item["value"]
            for item in authenticated_cookies + form_cookies + get_cookies
            if item["name"] == "PHPSESSID"
        }
        assert not any(value in json.dumps(identities) for value in cookie_values)

        post_replay = client.post(
            f"/api/requests/{post_request_id}/replay",
            json={"identity_id": form_identity},
        )
        assert post_replay.status_code == 201
        assert post_replay.json()["response_status"] == 200
        assert post_replay.json()["auth_source"] == "identity"
        assert post_replay.json()["method"] == "GET"
        assert post_replay.json()["request_body"] is None
        assert post_replay.json()["redirect_chain"]
        assert post_replay.json()["url"].endswith("security.php")
        assert "impossible" in post_replay.json()["response_body"]

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
        assert comparison_body["result"]["diff"]["json"]["present_a"] is False
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
        assert row["cells"][anonymous["id"]]["status"] == 200

        comparison_evidence = client.post(
            f"/api/engagements/{engagement_id}/evidence",
            json={
                "evidence_type": "Response Comparison",
                "title": "Authenticated and anonymous HTML comparison",
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
                "note": "Confirmed from the captured response",
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
                "affected_endpoints": ["/login.php"],
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
    assert password not in persisted_text
    assert not any(value in persisted_text for value in cookie_values)
