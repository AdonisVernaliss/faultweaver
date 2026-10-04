from __future__ import annotations

import http.client
import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from urllib.parse import urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from faultweaver.app import create_app
from faultweaver.config import Settings

from demo.app import create_server, validate_bind_host


@contextmanager
def running_demo() -> Generator[tuple[str, object]]:
    server = create_server("127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    parsed = urlsplit(base_url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def json_request(
    base_url: str, path: str, *, token: str | None = None
) -> tuple[int, dict[str, object]]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status, _, body = request(base_url, path, headers=headers)
    return status, json.loads(body)


def test_demo_surface_is_deterministic_and_explicitly_vulnerable() -> None:
    with running_demo() as (base_url, _):
        status, headers, body = request(base_url, "/")
        config_status, config = json_request(base_url, "/api/public-config")
        error_status, _, error_body = request(base_url, "/debug/error")
        _, _, sitemap = request(
            base_url, "/sitemap.xml", headers={"Host": "unsafe/<tag>"}
        )

    page = body.decode()
    assert status == 200
    assert headers["X-Faultweaver-Demo"] == "deliberately-vulnerable"
    assert "Content-Security-Policy" not in headers
    assert headers["Set-Cookie"] == "session=guest; Path=/"
    assert 'href="/api/invoices/1001"' in page
    assert 'href="http://127.0.0.1:9/outside"' in page
    assert '<form method="post" action="/session">' in page
    assert config_status == 200
    assert config == {"environment": "demo", "api_token": "synthetic-placeholder"}
    assert error_status == 500
    assert "Traceback (most recent call last)" in error_body.decode()
    assert "/srv/app/demo.py" in error_body.decode()
    assert "unsafe/<tag>" not in sitemap.decode()


def test_horizontal_and_admin_authorization_failures_are_reproducible() -> None:
    with running_demo() as (base_url, _):
        anonymous_status, _ = json_request(base_url, "/api/invoices/1001")
        alice_status, alice_invoice = json_request(
            base_url, "/api/invoices/1001", token="demo-alice-token"
        )
        bob_status, bob_invoice = json_request(
            base_url, "/api/invoices/1001", token="demo-bob-token"
        )
        _, alice_list = json_request(
            base_url, "/api/invoices", token="demo-alice-token"
        )
        _, bob_list = json_request(base_url, "/api/invoices", token="demo-bob-token")
        bob_admin_status, bob_admin = json_request(
            base_url, "/api/admin/audit/2026", token="demo-bob-token"
        )
        admin_status, admin = json_request(
            base_url, "/api/admin/audit/2026", token="demo-admin-token"
        )

    assert anonymous_status == 401
    assert alice_status == bob_status == 200
    assert alice_invoice == bob_invoice
    assert [item["id"] for item in alice_list["invoices"]] == [1001]
    assert [item["id"] for item in bob_list["invoices"]] == [2002]
    assert bob_admin_status == admin_status == 200
    assert bob_admin == admin


def test_login_uses_public_demo_credentials_and_weak_cookie() -> None:
    with running_demo() as (base_url, _):
        encoded = urlencode({"username": "alice", "password": "demo-alice"}).encode()
        status, headers, _ = request(
            base_url,
            "/session",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=encoded,
        )
        invalid_status, _, _ = request(
            base_url,
            "/session",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=urlencode({"username": "alice", "password": "wrong"}).encode(),
        )

    assert status == 303
    assert headers["Location"] == "/dashboard"
    assert headers["Set-Cookie"] == "session=alice; Path=/"
    assert "HttpOnly" not in headers["Set-Cookie"]
    assert invalid_status == 401


def test_non_loopback_binding_requires_explicit_override() -> None:
    validate_bind_host("127.0.0.1", allow_non_loopback=False)
    validate_bind_host("::1", allow_non_loopback=False)
    validate_bind_host("0.0.0.0", allow_non_loopback=True)
    with pytest.raises(ValueError, match="loopback"):
        validate_bind_host("0.0.0.0", allow_non_loopback=False)


def test_faultweaver_workflow_against_demo(tmp_path: Path) -> None:
    with running_demo() as (base_url, demo_server):
        parsed = urlsplit(base_url)
        app = create_app(
            Settings(
                database_url=f"sqlite:///{tmp_path / 'faultweaver.db'}",
                allowed_origins=("http://localhost:5173",),
            )
        )
        with TestClient(app) as client:
            engagement = client.post(
                "/api/engagements",
                json={"name": "Deliberately vulnerable demo validation"},
            ).json()
            engagement_id = engagement["id"]
            scope = client.post(
                f"/api/engagements/{engagement_id}/scopes",
                json={
                    "scheme": "http",
                    "hostname": parsed.hostname,
                    "port": parsed.port,
                    "path_prefix": "/",
                },
            )
            assert scope.status_code == 201
            run = client.post(
                f"/api/engagements/{engagement_id}/assessments",
                json={
                    "target_url": base_url,
                    "max_pages": 20,
                    "max_depth": 3,
                    "max_requests": 20,
                    "requests_per_second": 20,
                    "concurrency": 2,
                    "request_timeout_seconds": 2,
                },
            ).json()
            deadline = monotonic() + 8
            while monotonic() < deadline:
                detail = client.get(
                    f"/api/engagements/{engagement_id}/assessments/{run['id']}"
                ).json()
                if detail["status"] in {"Completed", "Failed", "Stopped"}:
                    break
                sleep(0.05)
            assert detail["status"] == "Completed"
            assert detail["failed_request_count"] == 0
            assert any(
                item["state"] == "skipped"
                and item["canonical_url"].endswith(":9/outside")
                for item in detail["discoveries"]
            )
            check_ids = {item["check_id"] for item in detail["observations"]}
            assert {
                "headers.content-security-policy",
                "cookies.session-flags",
                "content.sensitive-field-names",
                "disclosure.internal-path",
                "disclosure.verbose-error",
            }.issubset(check_ids)

            requests = client.get(
                f"/api/engagements/{engagement_id}/requests?source=crawler"
            ).json()["items"]
            invoice_request = next(
                item for item in requests if item["path"] == "/api/invoices/1001"
            )
            audit_request = next(
                item for item in requests if item["path"] == "/api/admin/audit/2026"
            )
            identity_ids = []
            for name, token in (
                ("Demo Alice", "demo-alice-token"),
                ("Demo Bob", "demo-bob-token"),
                ("Demo Administrator", "demo-admin-token"),
            ):
                identity = client.post(
                    f"/api/engagements/{engagement_id}/identities",
                    json={"name": name, "bearer_token": token},
                )
                assert identity.status_code == 201
                identity_ids.append(identity.json()["id"])
            comparison = client.post(
                f"/api/requests/{invoice_request['id']}/compare",
                json={
                    "identity_a_id": identity_ids[0],
                    "identity_b_id": identity_ids[1],
                },
            )
            assert comparison.status_code == 201
            assert comparison.json()["candidate"]["category"] == "authorization"
            admin_comparison = client.post(
                f"/api/requests/{audit_request['id']}/compare",
                json={
                    "identity_a_id": identity_ids[0],
                    "identity_b_id": identity_ids[2],
                },
            )
            assert admin_comparison.status_code == 201
            assert admin_comparison.json()["candidate"]["category"] == "authorization"
            surface = client.get(
                f"/api/engagements/{engagement_id}/attack-surface?source=crawler"
            ).json()
            assert any(
                item["path_template"] == "/api/invoices/1001" for item in surface
            )

        requested = list(demo_server.request_log)

    assert not any(method == "POST" for method, _ in requested)
    assert not any(path == "/assets/app.css" for _, path in requested)
