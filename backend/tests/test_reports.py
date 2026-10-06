import json

import pytest
from fastapi.testclient import TestClient

from faultweaver.attack_chains.models import AttackChain, AttackChainStep
from faultweaver.engagements.models import Engagement
from faultweaver.findings.models import Evidence, Finding, Retest, retest_evidence
from faultweaver.scope.models import ScopeRule


@pytest.fixture
def report_scenario(app_client: TestClient) -> dict:
    with app_client.app.state.session_factory() as session:
        session.add_all(
            [
                Engagement(id="northstar", name="Northstar Billing", status="reporting"),
                Engagement(id="other", name="Other synthetic assessment"),
            ]
        )
        session.flush()
        session.add(
            ScopeRule(
                engagement_id="northstar",
                scheme="https",
                hostname="billing.test",
                port=443,
                path_prefix="/api",
            )
        )
        for number, severity in enumerate(["Low", "High", "Informational"], 1):
            session.add(
                Finding(
                    id=f"finding-{number}",
                    engagement_id="northstar",
                    display_id=f"FW-{number:03}",
                    sequence_number=number,
                    title=f"Synthetic {severity} finding",
                    category="Authorization",
                    severity=severity,
                    description="Manually verified synthetic case.",
                    impact="Fictional tenant data.",
                    affected_asset="billing.test",
                    reproduction_steps=[
                        "Authenticate as the synthetic tenant.",
                        "Review the captured response.",
                    ],
                    remediation="Verify resource ownership.",
                )
            )
        session.add(
            Finding(
                id="foreign-finding",
                engagement_id="other",
                display_id="FW-001",
                sequence_number=1,
                title="Other finding",
                category="Test",
                severity="High",
            )
        )
        session.flush()
        for number in [1, 2]:
            session.add(
                Evidence(
                    id=f"evidence-{number}",
                    engagement_id="northstar",
                    display_id=f"EV-{number:03}",
                    sequence_number=number,
                    finding_id="finding-2",
                    evidence_type="HTTP Request/Response",
                    title=f"Synthetic evidence {number}",
                    snapshot={
                        "exchange": {
                            "method": "GET",
                            "url": "https://billing.test/api/invoices?token=report-query-secret",
                            "request_headers": [
                                {"name": "Authorization", "value": "Bearer report-header-secret"}
                            ],
                            "request_body": '{"password":"report-password-secret"}',
                            "response_status": 200,
                            "response_headers": [],
                            "response_body": '<script>alert("report-target")</script>' + "x" * 6000,
                        }
                    },
                )
            )
        session.add(
            Retest(
                id="retest-1",
                engagement_id="northstar",
                finding_id="finding-2",
                display_id="RT-001",
                sequence_number=1,
                status="Still Vulnerable",
                operator_notes="Target unchanged.",
            )
        )
        session.add(
            AttackChain(
                id="chain-1",
                engagement_id="northstar",
                display_id="AC-001",
                sequence_number=1,
                title="Synthetic tenant path",
                status="Validated",
                resulting_impact="Fictional invoice exposure.",
            )
        )
        session.flush()
        session.execute(
            retest_evidence.insert().values(retest_id="retest-1", evidence_id="evidence-2")
        )
        session.add_all(
            [
                AttackChainStep(
                    attack_chain_id="chain-1",
                    position=1,
                    step_type="Finding",
                    finding_id="finding-1",
                ),
                AttackChainStep(
                    attack_chain_id="chain-1",
                    position=2,
                    step_type="Intermediate",
                    title="Change context",
                ),
                AttackChainStep(
                    attack_chain_id="chain-1",
                    position=3,
                    step_type="Finding",
                    finding_id="finding-2",
                ),
            ]
        )
        session.commit()
    return {"base": "/api/engagements/northstar/reports"}


def create_report(client, base, **values):
    response = client.post(base, json={"title": "Northstar security assessment", **values})
    assert response.status_code == 201, response.text
    return response.json()


def test_report_lifecycle_and_engagement_isolation(app_client, report_scenario):
    base = report_scenario["base"]
    report = create_report(app_client, base)
    path = base + "/" + report["id"]
    assert report["display_id"] == "REP-001"
    assert report["status"] == "Draft"
    assert create_report(app_client, base)["display_id"] == "REP-002"
    assert app_client.get(f"/api/engagements/other/reports/{report['id']}").status_code == 404
    assert (
        app_client.patch(
            path, json={"version": report["version"], "finding_ids": ["foreign-finding"]}
        ).status_code
        == 422
    )
    assert (
        app_client.patch(
            path, json={"version": report["version"], "status": "Generated"}
        ).status_code
        == 422
    )
    ready = app_client.patch(path, json={"version": report["version"], "status": "Ready"})
    assert ready.status_code == 200
    assert (
        app_client.patch(path, json={"version": report["version"], "title": "Stale"}).status_code
        == 409
    )
    archived = app_client.patch(
        path, json={"version": ready.json()["version"], "status": "Archived"}
    ).json()
    assert (
        app_client.post(path + "/generate", json={"version": archived["version"]}).status_code
        == 409
    )
    assert app_client.get(base).json() == [app_client.get(base).json()[0]]
    assert len(app_client.get(base + "?include_archived=true").json()) == 2


def test_canonical_document_order_summaries_evidence_and_retests(app_client, report_scenario):
    base = report_scenario["base"]
    report = create_report(app_client, base, executive_summary="Operator interpretation.")
    result = app_client.get(base + "/" + report["id"] + "/preview")
    assert result.status_code == 200, result.text
    doc = result.json()
    assert doc["report_schema_version"] == "1.0"
    assert doc["report"]["executive_summary"] == "Operator interpretation."
    assert [f["display_id"] for f in doc["findings"]] == ["FW-002", "FW-001", "FW-003"]
    assert doc["summary"]["severity"] == {
        "Critical": 0,
        "High": 1,
        "Medium": 0,
        "Low": 1,
        "Informational": 1,
    }
    assert doc["summary"]["retested_findings"] == 1
    assert doc["findings"][0]["finding_evidence_ids"] == ["EV-001", "EV-002"]
    assert doc["retests"][0]["evidence_ids"] == ["EV-002"]
    assert [s["kind"] for s in doc["attack_chains"][0]["steps"]] == [
        "Finding",
        "Intermediate",
        "Finding",
    ]
    assert any(x["truncated"] for x in doc["evidence"][0]["excerpts"])
    for secret in ["report-query-secret", "report-header-secret", "report-password-secret"]:
        assert secret not in result.text


def test_report_snapshot_remains_immutable_after_source_and_draft_changes(
    app_client, report_scenario
):
    base = report_scenario["base"]
    report = create_report(app_client, base)
    path = base + "/" + report["id"]
    generated = app_client.post(path + "/generate", json={"version": report["version"]})
    assert generated.status_code == 201, generated.text
    revision = generated.json()
    assert revision["revision"] == 1
    old = app_client.get(path + "/revisions/1").json()
    app_client.patch(
        "/api/engagements/northstar/findings/finding-2", json={"title": "Changed source"}
    )
    current = app_client.get(path).json()
    edited = app_client.patch(
        path, json={"version": current["version"], "executive_summary": "Updated interpretation"}
    ).json()
    assert edited["status"] == "Draft"
    assert app_client.get(path + "/revisions/1").json() == old
    second = app_client.post(path + "/generate", json={"version": edited["version"]}).json()
    assert second["revision"] == 2
    assert len(app_client.get(path + "/revisions").json()) == 2
    assert app_client.get(path + "/revisions/2").json()["findings"][0]["title"] == "Changed source"
    assert all("document" not in item for item in app_client.get(path + "/revisions").json())
    assert "snapshot" not in app_client.get(base).text


def test_report_inclusion_and_validation(app_client, report_scenario):
    base = report_scenario["base"]
    report = create_report(app_client, base, finding_ids=["finding-1"], attack_chain_ids=[])
    path = base + "/" + report["id"]
    assert len(app_client.get(path + "/preview").json()["findings"]) == 1
    assert (
        app_client.patch(path, json={"version": 1, "attack_chain_ids": ["chain-1"]}).status_code
        == 422
    )
    assert app_client.post(base, json={"title": "  "}).status_code == 422
    assert (
        app_client.post(base, json={"title": "Test", "output_path": "../../other"}).status_code
        == 422
    )
    report = create_report(app_client, "/api/engagements/other/reports")
    other = f"/api/engagements/other/reports/{report['id']}"
    assert app_client.post(other + "/generate", json={"version": 1}).status_code == 422


def test_report_json_export_is_versioned_and_deterministic(app_client, report_scenario):
    base = report_scenario["base"]
    report = create_report(app_client, base, title="../../arbitrary <script>report</script>")
    path = base + "/" + report["id"]
    assert app_client.post(path + "/generate", json={"version": 1}).status_code == 201
    one = app_client.get(path + "/revisions/1/export/json")
    two = app_client.get(path + "/revisions/1/export/json")
    assert one.status_code == 200
    assert one.content == two.content
    assert (
        one.headers["content-disposition"] == 'attachment; filename="faultweaver-REP-001-r1.json"'
    )
    assert json.loads(one.text)["report_schema_version"] == "1.0"
    assert app_client.get(path + "/revisions/1/export/zip").status_code == 422


def test_report_schema_contract(app_client, report_scenario):
    schema = app_client.get("/api/report-schema").json()
    assert schema["properties"]["report_schema_version"]["const"] == "1.0"
    assert schema["additionalProperties"] is False
    options = app_client.get(report_scenario["base"] + "/options").json()
    assert len(options["findings"]) == 3
    assert options["findings"][0]["gaps"] == ["Evidence"]
    assert "description" not in options["findings"][0]
    assert len(options["attack_chains"]) == 1
    assert app_client.get("/api/engagements/other/reports/options").json()["attack_chains"] == []
    assert set(schema["required"]) == {
        "application_version",
        "report",
        "engagement",
        "scope",
        "summary",
        "findings",
        "evidence",
        "attack_chains",
        "retests",
        "assessments",
        "warnings",
    }


@pytest.mark.parametrize("format_name", ["html", "md", "json"])
def test_report_exports_share_content_and_reject_injection(
    app_client, report_scenario, format_name
):
    from html.parser import HTMLParser

    base = report_scenario["base"]
    malicious = '<script>alert(1)</script><img src=x onerror="alert(2)">'
    report = create_report(
        app_client,
        base,
        executive_summary=malicious,
        limitations="[click](javascript:alert(1))\n```\n# injected heading",
    )
    path = base + "/" + report["id"]
    assert app_client.post(path + "/generate", json={"version": 1}).status_code == 201
    response = app_client.get(path + "/revisions/1/export/" + format_name)
    assert response.status_code == 200
    assert response.content == app_client.get(path + "/revisions/1/export/" + format_name).content
    for value in [
        "FW-001",
        "FW-002",
        "EV-001",
        "AC-001",
        "RT-001",
        "Still Vulnerable",
        "Scope",
        "Northstar",
    ]:
        assert value.lower() in response.text.lower()
    for secret in ["report-query-secret", "report-header-secret", "report-password-secret"]:
        assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    if format_name == "html":

        class Inspector(HTMLParser):
            def handle_starttag(self, tag, attrs):
                assert tag not in {"script", "img", "iframe", "object", "embed", "form"}
                assert not any(k.startswith("on") for k, _ in attrs)
                assert all(not v or not v.lower().startswith("javascript:") for _, v in attrs)

        Inspector().feed(response.text)
        assert "&lt;script&gt;" in response.text
        assert "@media print" in response.text
        assert 'href="#FW-002"' in response.text
    if format_name == "md":
        assert malicious not in response.text
        # Literal target HTML is permitted only inside safely bounded code fences.
        import re

        prose = re.sub(r"(?ms)^(`{3,})text\n.*?^\1\n", "", response.text)
        assert "<script>" not in prose
        assert "\n# injected heading" not in response.text
        assert "1. Authenticate as the synthetic tenant." in response.text


def test_report_export_path_and_preview_safety(app_client, report_scenario):
    from fastapi import HTTPException

    from faultweaver.reports.router import export_filename

    for display_id in ["../../report", "/tmp/report", "REP-1\r\nX-Injected: bad"]:
        with pytest.raises(HTTPException):
            export_filename(display_id, 1, "html")
    base = report_scenario["base"]
    report = create_report(app_client, base)
    response = app_client.get(base + "/" + report["id"] + "/preview/html")
    assert response.status_code == 200
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "sandbox" in response.headers["content-security-policy"]
    assert "DRAFT PREVIEW" in response.text


def test_report_candidates_are_not_findings_and_archived_defaults(app_client, report_scenario):
    from faultweaver.engagements.models import utc_now
    from tests.test_finding_lifecycle import create_candidate
    from tests.test_http_import import authorize

    authorize(app_client, "northstar")
    candidate = create_candidate(app_client, "northstar")["candidate"]
    app_client.post(
        f"/api/engagements/northstar/candidates/{candidate['id']}/review",
        json={"decision": "False Positive", "note": "Expected shared data."},
    )
    with app_client.app.state.session_factory() as session:
        session.get(Finding, "finding-1").archived_at = utc_now()
        session.get(Finding, "finding-2").status = "Accepted Risk"
        session.get(Finding, "finding-3").status = "Fixed"
        session.commit()
    base = report_scenario["base"]
    report = create_report(app_client, base)
    doc = app_client.get(base + "/" + report["id"] + "/preview").json()
    assert doc["summary"]["finding_count"] == 2
    assert [f["status"] for f in doc["findings"]] == ["Accepted Risk", "Fixed"]
    assert doc["summary"]["severity"]["High"] == 1
    assert doc["attack_chains"] == []
    assert any("related Finding" in warning for warning in doc["warnings"])
    report = create_report(app_client, base, include_archived=True, include_informational=False)
    doc = app_client.get(base + "/" + report["id"] + "/preview").json()
    assert [f["display_id"] for f in doc["findings"]] == ["FW-002", "FW-001"]
    assert doc["findings"][1]["archived"] is True
    assert len(doc["attack_chains"]) == 1


def test_report_draft_chain_requires_explicit_inclusion(app_client, report_scenario):
    with app_client.app.state.session_factory() as session:
        session.get(AttackChain, "chain-1").status = "Draft"
        session.commit()
    base = report_scenario["base"]
    report = create_report(app_client, base)
    assert not app_client.get(base + "/" + report["id"] + "/preview").json()["attack_chains"]
    report = create_report(
        app_client, base, include_draft_chains=True, attack_chain_ids=["chain-1"]
    )
    assert (
        app_client.get(base + "/" + report["id"] + "/preview").json()["attack_chains"][0]["status"]
        == "Draft"
    )


def test_report_upgrade_from_encrypted_0007_and_restart(tmp_path):
    import secrets

    from sqlalchemy import text

    from faultweaver.app import create_app
    from faultweaver.config import Settings
    from faultweaver.database import create_storage_engine
    from faultweaver.migrations.runner import upgrade_database
    from faultweaver.storage.keys import KeyMaterial, MemoryKeyProvider

    path = tmp_path / "upgrade.db"
    url = f"sqlite:///{path}"
    key = KeyMaterial.generate()
    engine = create_storage_engine(url, key)
    with engine.begin() as connection:
        upgrade_database(url, "0007", connection=connection)
        connection.execute(
            text(
                "INSERT INTO engagements (id,name,description,status,created_at,updated_at) "
                "VALUES ('preserved','Previous encrypted state','','reporting',"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()
    settings = Settings(database_url=url, allowed_origins=())
    marker = secrets.token_urlsafe(40)
    with TestClient(create_app(settings, key_provider=MemoryKeyProvider(key))) as client:
        assert client.get("/api/engagements/preserved").status_code == 200
        client.post(
            "/api/engagements/preserved/scopes",
            json={"scheme": "https", "hostname": "billing.test", "port": 443},
        )
        base = "/api/engagements/preserved/reports"
        report = create_report(client, base, executive_summary=marker)
        report_path = base + "/" + report["id"]
        assert client.post(report_path + "/generate", json={"version": 1}).status_code == 201
        exported = client.get(report_path + "/revisions/1/export/json").content
        assert (
            marker.encode() in exported
        )  # Unlabelled operator prose is confidential, not a credential classifier.
        with client.app.state.session_factory() as session:
            assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0008"
    assert marker.encode() not in path.read_bytes()
    with TestClient(create_app(settings, key_provider=MemoryKeyProvider(key))) as client:
        assert client.get(report_path + "/revisions/1/export/json").content == exported
        assert client.get(report_path).json()["status"] == "Generated"
        assert create_report(client, base)["display_id"] == "REP-002"


def test_reused_evidence_survives_retest_and_latest_only_selection(app_client, report_scenario):
    from datetime import UTC, datetime

    with app_client.app.state.session_factory() as session:
        session.get(Retest, "retest-1").tested_at = datetime(2026, 1, 1, tzinfo=UTC)
        session.add(
            Retest(
                id="retest-2",
                engagement_id="northstar",
                finding_id="finding-2",
                display_id="RT-002",
                sequence_number=2,
                status="Fixed",
                tested_at=datetime(2026, 2, 1, tzinfo=UTC),
            )
        )
        session.flush()
        session.execute(
            retest_evidence.insert().values(
                retest_id="retest-2",
                evidence_id="evidence-1",
            )
        )
        session.commit()
    base = report_scenario["base"]
    report = create_report(app_client, base, include_retest_history=False)
    doc = app_client.get(base + "/" + report["id"] + "/preview").json()
    assert [r["display_id"] for r in doc["retests"]] == ["RT-002"]
    assert doc["retests"][0]["evidence_ids"] == ["EV-001"]
    assert doc["findings"][0]["finding_evidence_ids"] == ["EV-001", "EV-002"]
    assert doc["findings"][0]["latest_retest"] == "Fixed"
    assert doc["findings"][0]["severity"] == "High"
    assert doc["summary"]["latest_retest_results"]["Fixed"] == 1


def test_report_rejects_corrupt_cross_engagement_evidence_links(app_client, report_scenario):
    from faultweaver.attack_chains.models import attack_chain_evidence

    base = report_scenario["base"]
    report = create_report(app_client, base)
    with app_client.app.state.session_factory() as session:
        session.add(
            Evidence(
                id="foreign-evidence",
                engagement_id="other",
                display_id="EV-001",
                sequence_number=1,
                title="Foreign confidential evidence",
                evidence_type="Text",
                snapshot={"text": "foreign-confidential-marker"},
            )
        )
        session.flush()
        session.execute(
            attack_chain_evidence.insert().values(
                attack_chain_id="chain-1",
                evidence_id="foreign-evidence",
            )
        )
        session.commit()
    response = app_client.get(base + "/" + report["id"] + "/preview")
    assert response.status_code == 422
    assert "foreign-confidential-marker" not in response.text


def test_report_never_reads_live_http_or_identity_payloads(app_client, report_scenario):
    from sqlalchemy import event

    statements = []
    with app_client.app.state.session_factory() as session:
        engine = session.get_bind()

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        base = report_scenario["base"]
        report = create_report(app_client, base)
        assert app_client.get(base + "/" + report["id"] + "/preview").status_code == 200
        assert app_client.get(base + "/options").status_code == 200
        assert not any("http_exchanges" in s or "identities" in s for s in statements)
        statements.clear()
        assert app_client.get(base).status_code == 200
        assert not any("reports.content" in statement for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not any("http_exchanges" in s or "identities" in s for s in statements)


def test_markdown_fence_cannot_be_closed_by_target_evidence():
    from faultweaver.reports.rendering import Writer

    writer = Writer("md")
    writer.code("```\n<script>unsafe()</script>\n``````\n![x](https://external.test)")
    rendered = writer.parts[0]
    assert rendered.startswith("```````text\n")
    assert rendered.rstrip().endswith("```````")
