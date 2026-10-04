from __future__ import annotations

import json
import os
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from faultweaver.app import create_app
from faultweaver.config import Settings

EXPECTED_VERSION = "20.2.0"
TERMINAL_STATES = {"Completed", "Failed", "Stopped"}


def _target_url() -> str:
    target = os.environ.get("FAULTWEAVER_JUICE_SHOP_URL")
    if not target:
        pytest.skip("set FAULTWEAVER_JUICE_SHOP_URL to run this external-lab test")
    parsed = urlsplit(target)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("Juice Shop compatibility tests require an HTTP loopback target")
    return target.rstrip("/")


def _register_and_login(target: httpx.Client, label: str) -> tuple[str, str]:
    email = f"compat-{label}-{secrets.token_hex(6)}@example.test"
    password = secrets.token_urlsafe(18)
    questions = target.get("/api/SecurityQuestions/")
    questions.raise_for_status()
    registered = target.post(
        "/api/Users/",
        json={
            "email": email,
            "password": password,
            "passwordRepeat": password,
            "securityQuestion": questions.json()["data"][0],
            "securityAnswer": f"answer-{secrets.token_hex(6)}",
        },
    )
    registered.raise_for_status()
    login = target.post("/rest/user/login", json={"email": email, "password": password})
    login.raise_for_status()
    return email, login.json()["authentication"]["token"]


def _headers(headers: httpx.Headers) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in headers.multi_items()]


def _har_entry(response: httpx.Response) -> dict[str, object]:
    request = response.request
    return {
        "startedDateTime": datetime.now(UTC).isoformat(),
        "time": 0,
        "request": {
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
        },
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
    pytest.fail("Juice Shop baseline assessment did not finish within 30 seconds")


def _create_identity(
    client: TestClient, engagement_id: str, name: str, session_token: str
) -> str:
    response = client.post(
        f"/api/engagements/{engagement_id}/identities",
        json={"name": name, "cookies": [{"name": "token", "value": session_token}]},
    )
    assert response.status_code == 201
    assert session_token not in response.text
    return response.json()["id"]


def test_real_juice_shop_workflow(tmp_path: Path) -> None:
    base_url = _target_url()
    parsed_target = urlsplit(base_url)
    with httpx.Client(base_url=base_url, timeout=10) as target:
        version = target.get("/rest/admin/application-version")
        version.raise_for_status()
        assert version.json()["version"] == EXPECTED_VERSION

        user_a_email, token_a = _register_and_login(target, "a")
        user_b_email, token_b = _register_and_login(target, "b")
        search = target.get("/rest/products/search", params={"q": "apple"})
        whoami_a = target.get(
            "/rest/user/whoami",
            headers={
                "Cookie": f"token={token_a}",
                "Authorization": f"Bearer {token_a}",
            },
        )
        whoami_b = target.get(
            "/rest/user/whoami",
            headers={
                "Cookie": f"token={token_b}",
                "Authorization": f"Bearer {token_b}",
            },
        )
        for response in (search, whoami_a, whoami_b):
            response.raise_for_status()
        assert whoami_a.json()["user"]["email"] == user_a_email
        assert whoami_b.json()["user"]["email"] == user_b_email

    har = _har_document([search, whoami_a, whoami_b])
    database_url = f"sqlite:///{tmp_path / 'juice-shop-compat.db'}"
    settings = Settings(
        database_url=database_url, allowed_origins=("http://localhost:5173",)
    )

    with TestClient(create_app(settings)) as client:
        engagement = client.post(
            "/api/engagements",
            json={
                "name": "OWASP Juice Shop compatibility",
                "description": "Authorized loopback-only external lab validation",
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
                "target_url": f"{base_url}/",
                "max_pages": 12,
                "max_depth": 2,
                "max_requests": 20,
                "requests_per_second": 10,
                "concurrency": 2,
                "max_query_variants_per_path": 2,
            },
        )
        assert started.status_code == 201
        run = _wait_for_run(client, engagement_id, started.json()["id"])
        assert run["status"] == "Completed"
        assert run["request_count"] >= 1
        requested = [
            item for item in run["discoveries"] if item["state"] == "requested"
        ]
        assert requested
        assert all(
            urlsplit(item["url"]).hostname == parsed_target.hostname
            for item in requested
        )

        har_preview = client.post(
            f"/api/engagements/{engagement_id}/imports/har/preview",
            json={"content": har, "filename": "juice-shop-session.har"},
        )
        assert har_preview.status_code == 200
        assert har_preview.json()["accepted_count"] == 3
        assert har_preview.json()["response_count"] == 3
        assert token_a not in har_preview.text
        har_import = client.post(
            f"/api/engagements/{engagement_id}/imports/har",
            json={"content": har, "filename": "juice-shop-session.har"},
        )
        assert har_import.status_code == 201
        assert har_import.json()["batch"]["display_id"] == "IMP-001"

        curl_command = (
            f"curl '{base_url}/rest/user/whoami' "
            f"--cookie 'token={token_a}' -H 'Accept: application/json'"
        )
        curl_preview = client.post(
            f"/api/engagements/{engagement_id}/imports/curl/preview",
            json={"content": curl_command},
        )
        assert curl_preview.status_code == 200
        assert token_a not in curl_preview.text
        curl_import = client.post(
            f"/api/engagements/{engagement_id}/imports/curl",
            json={"content": curl_command, "filename": "browser-copy.txt"},
        )
        assert curl_import.status_code == 201
        assert curl_import.json()["batch"]["display_id"] == "IMP-002"
        request_id = curl_import.json()["request_ids"][0]
        request_detail = client.get(f"/api/requests/{request_id}")
        assert request_detail.json()["source"] == "curl"
        assert token_a not in request_detail.text
        assert "[REDACTED]" in request_detail.text

        surface = client.get(f"/api/engagements/{engagement_id}/attack-surface").json()
        whoami_surface = next(
            item for item in surface if item["path_template"] == "/rest/user/whoami"
        )
        assert set(whoami_surface["sources"]) == {"curl", "har"}
        assert whoami_surface["observed_request_count"] == 3

        identity_a = _create_identity(client, engagement_id, "user-a", token_a)
        identity_b = _create_identity(client, engagement_id, "user-b", token_b)
        identities = client.get(f"/api/engagements/{engagement_id}/identities").json()
        anonymous = next(item for item in identities if item["is_anonymous"])
        assert {item["name"] for item in identities} == {
            "Anonymous",
            "user-a",
            "user-b",
        }
        assert token_a not in json.dumps(identities)
        assert token_b not in json.dumps(identities)

        replay_a = client.post(
            f"/api/requests/{request_id}/replay", json={"identity_id": identity_a}
        )
        replay_anonymous = client.post(
            f"/api/requests/{request_id}/replay", json={"identity_id": anonymous["id"]}
        )
        assert replay_a.status_code == 201
        assert replay_a.json()["response_status"] == 200
        assert replay_a.json()["auth_source"] == "identity"
        assert replay_anonymous.status_code == 201

        comparison = client.post(
            f"/api/requests/{request_id}/compare",
            json={"identity_a_id": identity_a, "identity_b_id": identity_b},
        )
        assert comparison.status_code == 201
        comparison_body = comparison.json()
        assert comparison_body["replay_a"]["response_status"] == 200
        assert comparison_body["replay_b"]["response_status"] == 200
        assert comparison_body["result"]["diff"]["json"] is not None
        assert comparison_body["candidate"] is None
        comparison_id = comparison_body["id"]

        matrix = client.get(
            f"/api/engagements/{engagement_id}/authorization-matrix"
        ).json()
        row = next(
            item for item in matrix["rows"] if item["original_request_id"] == request_id
        )
        assert row["cells"][identity_a]["status"] == 200
        assert row["cells"][identity_b]["status"] == 200
        assert row["cells"][anonymous["id"]]["status"] == 200

        comparison_evidence = client.post(
            f"/api/engagements/{engagement_id}/evidence",
            json={
                "evidence_type": "Response Comparison",
                "title": "Synthetic identity response comparison",
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
        finding = client.post(
            f"/api/engagements/{engagement_id}/candidates/{baseline_candidate['id']}/promote",
            json={
                "title": "Content Security Policy header is absent",
                "category": "Security Misconfiguration",
                "severity": "Low",
                "affected_asset": parsed_target.netloc,
                "affected_endpoints": ["/"],
                "description": "The HTML application shell omits Content-Security-Policy.",
                "impact": "The browser has fewer defense-in-depth controls.",
                "reproduction_steps": [
                    "Request the application shell and inspect its headers."
                ],
                "remediation": "Define, test, and enforce a restrictive Content-Security-Policy.",
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
                "title": "Application shell response without CSP",
                "source_exchange_id": baseline_candidate["original_exchange_id"],
                "finding_id": finding_id,
            },
        )
        assert finding_evidence.status_code == 201
        assert finding_evidence.json()["display_id"] == "EV-002"
        evidence_id = finding_evidence.json()["id"]
        evidence_snapshot = finding_evidence.json()["snapshot"]

        chain = client.post(
            f"/api/engagements/{engagement_id}/attack-chains",
            json={
                "title": "Juice Shop compatibility finding path",
                "description": "Draft compatibility path with one confirmed finding.",
                "resulting_impact": "Not assessed as a multi-finding chain.",
            },
        )
        assert chain.status_code == 201
        chain_id = chain.json()["id"]
        chain_step = client.post(
            f"/api/engagements/{engagement_id}/attack-chains/{chain_id}/steps",
            json={"step_type": "Finding", "finding_id": finding_id},
        )
        assert chain_step.status_code == 201
        assert chain_step.json()["display_id"] == "AC-001"
        assert chain_step.json()["status"] == "Draft"

    with TestClient(create_app(settings)) as restarted:
        batches = restarted.get(f"/api/engagements/{engagement_id}/imports")
        persisted_comparison = restarted.get(f"/api/comparisons/{comparison_id}")
        persisted_finding = restarted.get(
            f"/api/engagements/{engagement_id}/findings/{finding_id}"
        )
        persisted_evidence = restarted.get(
            f"/api/engagements/{engagement_id}/evidence/{evidence_id}"
        )
        persisted_chain = restarted.get(
            f"/api/engagements/{engagement_id}/attack-chains/{chain_id}"
        )
        persisted_run = restarted.get(
            f"/api/engagements/{engagement_id}/assessments/{run['id']}"
        )

    assert [item["display_id"] for item in batches.json()] == ["IMP-002", "IMP-001"]
    assert persisted_comparison.status_code == 200
    assert persisted_finding.json()["display_id"] == "FW-001"
    assert persisted_evidence.json()["snapshot"] == evidence_snapshot
    assert persisted_chain.json()["display_id"] == "AC-001"
    assert persisted_run.json()["status"] == "Completed"
    persisted_text = "\n".join(
        response.text
        for response in (
            batches,
            persisted_comparison,
            persisted_finding,
            persisted_evidence,
            persisted_chain,
            persisted_run,
        )
    )
    assert token_a not in persisted_text
    assert token_b not in persisted_text
