from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from faultweaver.analysis.diffing import compare_responses
from faultweaver.analysis.normalization import normalize_response
from faultweaver.app import create_app
from faultweaver.assessments.discovery import discover_html
from faultweaver.config import Settings


def _target_url() -> str:
    target = os.environ.get("FAULTWEAVER_MUTILLIDAE_URL")
    if not target:
        pytest.skip("set FAULTWEAVER_MUTILLIDAE_URL to run this external-lab test")
    parsed = urlsplit(target)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.path not in {"", "/"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        pytest.fail("Mutillidae compatibility requires an HTTP loopback origin")
    return target.rstrip("/")


def _headers(headers: httpx.Headers) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in headers.multi_items()]


def _har(responses: list[httpx.Response]) -> str:
    entries = []
    for response in responses:
        request = response.request
        entry = {
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
                    "mimeType": response.headers.get("content-type", "text/plain"),
                    "text": response.text,
                },
                "redirectURL": response.headers.get("location", ""),
                "headersSize": -1,
                "bodySize": len(response.content),
            },
            "cache": {},
            "timings": {"send": -1, "wait": -1, "receive": -1},
        }
        if request.content:
            entry["request"]["postData"] = {
                "mimeType": request.headers.get("content-type", "text/plain"),
                "text": request.content.decode(),
            }
        entries.append(entry)
    return json.dumps(
        {
            "log": {
                "version": "1.2",
                "creator": {"name": "Compatibility", "version": "1"},
                "entries": entries,
            }
        }
    )


def _wait(client: TestClient, prefix: str, run_id: str) -> dict:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = client.get(f"{prefix}/assessments/{run_id}")
        assert result.status_code == 200
        run = result.json()
        if run["status"] in {"Completed", "Stopped", "Failed"}:
            assert run["status"] == "Completed"
            return run
        time.sleep(0.1)
    pytest.fail("bounded baseline did not finish")


def _normalized(response: httpx.Response):
    return normalize_response(
        status=response.status_code,
        headers=_headers(response.headers),
        body=response.text,
    )


def test_real_mutillidae_workflow(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = _target_url()
    origin = urlsplit(base)
    captured: list[httpx.Response] = []
    secret_values: set[str] = set()
    with httpx.Client(base_url=base, follow_redirects=False, timeout=20) as target:
        initial = target.get("/index.php")
        if (
            initial.status_code == 302
            and initial.headers.get("location") == "database-offline.php"
        ):
            # Ordinary initialization is allowed only for this fresh, owned lab.
            setup = target.get("/set-up-database.php")
            assert setup.status_code == 200
        home = target.get("/index.php")
        assert home.status_code == 200
        # The official www-2.12.7 tag at the pinned digest contains 2.12.8.
        assert "Version: 2.12.8" in home.text
        captured.append(home)
        registration = target.get("/index.php?page=register.php")
        captured.append(registration)
        token = re.search(r'name="csrf-token"[^>]*value="([^"]*)"', registration.text)
        csrf = token[1] if token else ""
        if csrf:
            secret_values.add(csrf)
        username = "compat" + secrets.token_hex(4)
        password = "P" + secrets.token_hex(8)
        secret_values.add(password)
        registered = target.post(
            "/index.php?page=register.php",
            data={
                "username": username,
                "password": password,
                "confirm_password": password,
                "firstname": "Synthetic",
                "lastname": "Tester",
                "my_signature": "Compatibility & plus+ % only",
                "csrf-token": csrf,
                "register-php-submit-button": "Create Account",
            },
        )
        assert registered.status_code == 200
        assert "created" in registered.text.lower()
        captured.append(registered)
        # Repeated and empty auxiliary fields test transport fidelity without
        # altering the login operation or submitting a command/upload payload.
        fields = [
            ("username", username),
            ("password", password),
            ("login-php-submit-button", "Login"),
            ("redirectPage", ""),
            ("note", "First"),
            ("note", "Last & plus+ %"),
            ("empty", ""),
        ]
        login_body = urlencode(fields)
        logged = target.post(
            "/index.php?page=login.php",
            content=login_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert logged.status_code == 302
        assert logged.headers["location"] == "index.php?popUpNotificationCode=AU1"
        captured.append(logged)
        landed = target.get("/" + logged.headers["location"])
        assert landed.status_code == 200
        assert landed.headers.get("logged-in-user") == username
        captured.append(landed)
        cookies = [
            {"name": c.name, "value": c.value}
            for c in target.cookies.jar
            if c.name == "PHPSESSID"
        ]
        assert len(cookies) == 1
        secret_values.update(c["value"] for c in cookies)
        cookie = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        query = urlencode(
            [
                ("page", "login.php"),
                ("note", "First"),
                ("note", "Last & plus+ %"),
                ("empty", ""),
            ]
        )
        queried = target.get("/index.php?" + query)
        captured.append(queried)
        parsed_forms = []
        for page in [
            "login.php",
            "document-viewer.php",
            "text-file-viewer.php",
            "upload-file.php",
        ]:
            response = target.get("/index.php?page=" + page)
            assert response.status_code == 200
            captured.append(response)
            parsed_forms.extend(discover_html(response.text, str(response.url)).forms)
        field_types = {f.input_type for form in parsed_forms for f in form.fields}
        assert {"hidden", "text", "password", "radio", "select", "file"} <= field_types
        assert {"GET", "POST"} <= {form.method for form in parsed_forms}
        assert "multipart/form-data" in {form.enctype for form in parsed_forms}
        assert all(
            "value" not in asdict(field)
            for form in parsed_forms
            for field in form.fields
        )

        empty_form = httpx.Request(
            "POST",
            base + "/index.php?page=upload-file.php",
            data={
                "UPLOAD_DIRECTORY": "/tmp",
                "MAX_FILE_SIZE": "1048576",
                "upload-file-php-submit-button": "Upload File",
            },
            files={"filename": ("empty.txt", b"", "application/octet-stream")},
        )
        # Match a browser's unselected file control. HTTPX omits filename=""
        # when given an empty filename directly, changing PHP's interpretation.
        empty_body = empty_form.read().replace(b'filename="empty.txt"', b'filename=""')
        multipart = target.post(
            "/index.php?page=upload-file.php",
            content=empty_body,
            headers={"Content-Type": empty_form.headers["content-type"]},
        )
        assert multipart.status_code == 200
        assert (
            "No file was uploaded" in multipart.text
        )  # PHP UPLOAD_ERR_NO_FILE; no file is supplied.
        captured.append(multipart)
        nested = target.get("/webservices/rest/ws-test-connectivity.php")
        assert nested.status_code == 200
        assert nested.json()["status"] == "OK"
        captured.append(nested)
        missing = target.get("/compatibility-missing-page")
        assert missing.status_code == 404
        assert "text/html" in missing.headers["content-type"]
        captured.append(missing)
        repeated = target.get("/index.php?" + query)
        # Exercise the normalizer on identical, naturally changing, and different
        # real HTML. Similarity is observed, never tuned to this application's layout.
        same = compare_responses(_normalized(queried), _normalized(queried))
        dynamic = compare_responses(_normalized(queried), _normalized(repeated))
        different = compare_responses(_normalized(queried), _normalized(missing))
        assert same["normalized_similarity"] == 1
        assert dynamic["normalized_similarity"] > 0.9
        assert different["status"]["changed"] is True
        assert different["body_size"]["delta"] != 0
        assert different["normalized_similarity"] < 0.5

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'mutillidae-compat.db'}",
        allowed_origins=("http://localhost:5173",),
    )
    with TestClient(create_app(settings)) as client:
        result = client.post(
            "/api/engagements",
            json={
                "name": "OWASP Mutillidae compatibility",
                "description": "Authorized local traditional HTTP workflow",
            },
        )
        assert result.status_code == 201
        engagement_id = result.json()["id"]
        prefix = f"/api/engagements/{engagement_id}"
        for path in [
            "/index.php",
            "/robots.txt",
            "/sitemap.xml",
            "/webservices/rest/ws-test-connectivity.php",
            "/compatibility-missing-page",
        ]:
            scope = client.post(
                f"{prefix}/scopes",
                json={
                    "scheme": "http",
                    "hostname": origin.hostname,
                    "port": origin.port or 80,
                    "path_prefix": path,
                },
            )
            assert scope.status_code == 201
        rejected = client.post(
            f"{prefix}/assessments", json={"target_url": base + "/outside-scope"}
        )
        assert rejected.status_code in {400, 403, 422}
        runs = []
        for page, depth in [
            ("login.php", 1),
            ("register.php", 0),
            ("document-viewer.php", 0),
        ]:
            started = client.post(
                f"{prefix}/assessments",
                json={
                    "target_url": base + "/index.php?page=" + page,
                    "max_pages": 4,
                    "max_depth": depth,
                    "max_requests": 6,
                    "requests_per_second": 4,
                    "concurrency": 1,
                    "max_query_variants_per_path": 2,
                    "inspect_site_metadata": page == "login.php",
                },
            )
            assert started.status_code == 201
            runs.append(_wait(client, prefix, started.json()["id"]))
        run = runs[0]
        assert all(1 <= r["request_count"] <= 6 for r in runs)
        assert any(d["reason"] == "query variation limit" for d in run["discoveries"])
        assert any(
            d["reason"] == "outside authorized scope" for d in run["discoveries"]
        )
        assert any(d["reason"] == "depth limit" for d in runs[1]["discoveries"])
        assert len({d["canonical_url"] for d in run["discoveries"]}) == len(
            run["discoveries"]
        )
        crawler = client.get(f"{prefix}/requests?source=crawler").json()["items"]
        assert all(r["method"] == "GET" and r["request_body"] is None for r in crawler)
        assert not any(
            "do=" in r["query"] or "set-up-database" in r["path"] for r in crawler
        )
        assert all((r["crawl_depth"] or 0) <= 1 for r in crawler)
        assert any(
            r["path"] == "/robots.txt" and r["response_status"] == 200 for r in crawler
        )
        assert any(
            r["path"] == "/sitemap.xml" and r["response_status"] == 404 for r in crawler
        )
        for current in runs:
            counts = Counter(
                urlsplit(r["url"]).path
                for r in crawler
                if r["assessment_run_id"] == current["id"]
            )
            assert counts["/index.php"] <= 2
        form_fields = [f for r in runs for form in r["forms"] for f in form["fields"]]
        assert {"hidden", "password", "radio", "textarea"} <= {
            f["type"] for f in form_fields
        }
        assert all("value" not in f for f in form_fields)
        assert any(o["occurrence_count"] > 1 for o in run["observations"])
        assert len({o["check_id"] for o in run["observations"]}) == len(
            run["observations"]
        )

        content = _har(captured)
        preview = client.post(
            f"{prefix}/imports/har/preview",
            json={"content": content, "filename": "mutillidae-http.har"},
        )
        assert preview.status_code == 200
        assert preview.json()["accepted_count"] == len(captured) == 13
        assert preview.json()["response_count"] == len(captured)
        assert preview.json()["skipped_count"] == 0
        imported = client.post(
            f"{prefix}/imports/har",
            json={"content": content, "filename": "mutillidae-http.har"},
        )
        assert imported.status_code == 201
        assert imported.json()["batch"]["display_id"] == "IMP-001"
        curl_commands = [
            f"curl {shlex.quote(base + '/index.php?' + query)} --cookie {shlex.quote(cookie)}",
            f"curl {shlex.quote(base + '/index.php?page=login.php')} --cookie {shlex.quote(cookie)} -H 'Content-Type: application/x-www-form-urlencoded' --data-raw {shlex.quote(login_body)}",
            f"curl {shlex.quote(base + '/index.php?page=upload-file.php')} --cookie {shlex.quote(cookie)} -H {shlex.quote('Content-Type: ' + multipart.request.headers['content-type'])} --data-binary {shlex.quote(multipart.request.content.decode())}",
        ]
        curl_ids = []
        for command in curl_commands:
            curl_preview = client.post(
                f"{prefix}/imports/curl/preview", json={"content": command}
            )
            assert curl_preview.status_code == 200
            added = client.post(
                f"{prefix}/imports/curl",
                json={"content": command, "filename": "copied-request.txt"},
            )
            assert added.status_code == 201
            curl_ids.append(added.json()["request_ids"][0])
        get_id, post_id, _multipart_id = curl_ids
        originals = [client.get(f"/api/requests/{rid}").json() for rid in curl_ids]
        assert parse_qsl(originals[0]["query"], keep_blank_values=True) == parse_qsl(
            query, keep_blank_values=True
        )
        assert parse_qsl(originals[1]["request_body"], keep_blank_values=True) == [
            (key, "[REDACTED]" if key == "password" else value) for key, value in fields
        ]
        assert originals[2]["request_body"] == multipart.request.content.decode()
        assert all(r["response_status"] is None for r in originals)

        identity = client.post(
            f"{prefix}/identities", json={"name": "synthetic-user", "cookies": cookies}
        )
        assert identity.status_code == 201
        identity_id = identity.json()["id"]
        anonymous_id = next(
            i["id"]
            for i in client.get(f"{prefix}/identities").json()
            if i["is_anonymous"]
        )
        for request_id in [get_id, post_id]:
            replay = client.post(
                f"/api/requests/{request_id}/replay", json={"identity_id": identity_id}
            )
            assert replay.status_code == 201
            actual = replay.json()
            assert actual["id"] != request_id
            assert actual["parent_exchange_id"] == request_id
            assert actual["response_status"] == 200
            assert actual["auth_source"] == "identity"
            assert username in actual["response_body"]
            if request_id == post_id:
                assert actual["redirect_chain"]
        assert [
            client.get(f"/api/requests/{rid}").json() for rid in curl_ids
        ] == originals
        outside = client.post(
            f"/api/requests/{get_id}/replay",
            json={"url": base + "/outside-scope", "identity_id": identity_id},
        )
        assert outside.status_code == 403

        # Protected form GET provides a real, normal authenticated/anonymous HTML comparison.
        protected_id = next(
            r["id"]
            for r in client.get(f"{prefix}/requests?q=upload-file&source=har").json()[
                "items"
            ]
            if r["method"] == "GET"
        )
        compared = client.post(
            f"/api/requests/{protected_id}/compare",
            json={"identity_a_id": identity_id, "identity_b_id": anonymous_id},
        )
        assert compared.status_code == 201
        comparison = compared.json()
        assert comparison["result"]["diff"]["redirects"]["changed"]
        assert comparison["result"]["diff"]["normalized_similarity"] < 1
        assert comparison["result"]["diff"]["body_size"]["delta"] != 0
        assert comparison["candidate"] is None
        matrix = client.get(f"{prefix}/authorization-matrix").json()
        row = next(
            r for r in matrix["rows"] if r["original_request_id"] == protected_id
        )
        assert (
            row["cells"][identity_id]["status"]
            == row["cells"][anonymous_id]["status"]
            == 200
        )

        surface = client.get(f"{prefix}/attack-surface").json()
        index_routes = [e for e in surface if e["path_template"] == "/index.php"]
        assert {e["method"] for e in index_routes} == {"GET", "POST"}
        assert (
            len(index_routes) == 2
        )  # Query-routed pages are not invented path templates.
        assert {"har", "curl", "crawler"} <= set(
            next(e for e in index_routes if e["method"] == "GET")["sources"]
        )
        candidates = client.get(f"{prefix}/candidates").json()
        candidate = next(
            c
            for c in candidates
            if c["assessment_run_id"] == run["id"]
            and c["title"] == "Content Security Policy is absent"
        )
        reviewed = client.post(
            f"{prefix}/candidates/{candidate['id']}/review",
            json={
                "decision": "Accepted",
                "note": "Confirmed missing header on the observed login response",
            },
        )
        assert reviewed.status_code == 200
        promoted = client.post(
            f"{prefix}/candidates/{candidate['id']}/promote",
            json={
                "title": "Content Security Policy is absent on the login response",
                "category": "Security Misconfiguration",
                "severity": "Low",
                "affected_asset": origin.netloc,
                "affected_endpoints": ["/index.php?page=login.php"],
                "description": "The captured login response has no Content-Security-Policy header.",
                "impact": "The browser lacks this defense-in-depth restriction on active content.",
                "reproduction_steps": [
                    "Request the login page and inspect the response headers."
                ],
                "remediation": "Develop and enforce a restrictive Content Security Policy appropriate to the application.",
                "references": ["https://owasp.org/www-project-secure-headers/"],
            },
        )
        assert promoted.status_code == 201
        finding = promoted.json()
        assert finding["display_id"] == "FW-001"
        evidence = client.post(
            f"{prefix}/evidence",
            json={
                "evidence_type": "HTTP Request/Response",
                "title": "Login response headers",
                "source_exchange_id": candidate["original_exchange_id"],
                "finding_id": finding["id"],
            },
        )
        assert evidence.status_code == 201
        comparison_evidence = client.post(
            f"{prefix}/evidence",
            json={
                "evidence_type": "Response Comparison",
                "title": "Normal session-gated HTML representations",
                "source_comparison_id": comparison["id"],
            },
        )
        assert comparison_evidence.status_code == 201
        snapshot = evidence.json()["snapshot"]
        public = "\n".join(
            [
                preview.text,
                imported.text,
                compared.text,
                promoted.text,
                evidence.text,
                comparison_evidence.text,
                json.dumps(originals),
            ]
        )
        for route in [
            "requests",
            "identities",
            "findings",
            "evidence",
            "candidates",
            f"findings/{finding['id']}",
            "attack-surface",
        ]:
            response = client.get(f"{prefix}/{route}")
            assert response.status_code == 200
            public += response.text
        assert not any(
            value in public or value in caplog.text for value in secret_values
        )

    with TestClient(create_app(settings)) as restarted:
        assert len(restarted.get(f"{prefix}/imports").json()) == 4
        assert (
            restarted.get(f"{prefix}/assessments/{run['id']}").json()["status"]
            == "Completed"
        )
        assert restarted.get(f"/api/comparisons/{comparison['id']}").status_code == 200
        assert (
            restarted.get(f"{prefix}/findings/{finding['id']}").json()["display_id"]
            == "FW-001"
        )
        saved = restarted.get(f"{prefix}/evidence/{evidence.json()['id']}")
        assert saved.json()["snapshot"] == snapshot
        assert not any(value in saved.text for value in secret_values)
        assert restarted.get(f"{prefix}/attack-chains").json() == []
