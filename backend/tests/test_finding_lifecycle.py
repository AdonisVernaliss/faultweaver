from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from faultweaver.findings.models import Evidence
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.redaction import REDACTED
from tests.test_differential_analysis import create_identity
from tests.test_engagements_and_scope import create_engagement
from tests.test_http_import import authorize
from tests.test_replay_and_persistence import import_request


def create_candidate(client: TestClient, engagement_id: str, path: str = "/api/orders/17") -> dict:
    request_id = import_request(client, engagement_id, path)
    first = create_identity(client, engagement_id, f"First {path}", f"first-{path}")
    second = create_identity(client, engagement_id, f"Second {path}", f"second-{path}")
    response = client.post(
        f"/api/requests/{request_id}/compare",
        json={"identity_a_id": first, "identity_b_id": second},
    )
    assert response.status_code == 201
    assert response.json()["candidate"] is not None
    return response.json()


def test_candidate_review_promotion_and_finding_history(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)
    comparison = create_candidate(app_client, engagement_id)
    candidate = comparison["candidate"]

    promoted = app_client.post(
        f"/api/engagements/{engagement_id}/candidates/{candidate['id']}/promote",
        json={
            "severity": "High",
            "affected_asset": "app.test",
            "affected_endpoints": ["/api/orders/17"],
            "description": "Cross-tenant order access was confirmed.",
            "impact": "A tenant can read another tenant's order.",
            "reproduction_steps": ["Replay the order request as another tenant."],
            "remediation": "Enforce ownership checks for every order lookup.",
        },
    )

    assert promoted.status_code == 201
    finding = promoted.json()
    assert finding["display_id"] == "FW-001"
    assert finding["candidate_id"] == candidate["id"]
    assert finding["supporting_comparison_id"] == comparison["id"]
    assert finding["history"][0]["event_type"] == "candidate_promoted"
    retained = app_client.get(
        f"/api/engagements/{engagement_id}/candidates/{candidate['id']}"
    ).json()
    assert retained["status"] == "promoted"
    assert retained["review_decision"] == "Confirmed"
    assert retained["finding_id"] == finding["id"]
    assert retained["original"]["id"] == comparison["original_exchange_id"]
    assert len(retained["supporting_replays"]) == 2
    assert {item["name"] for item in retained["identities"]} == {
        "First /api/orders/17",
        "Second /api/orders/17",
    }
    assert (
        app_client.post(
            f"/api/engagements/{engagement_id}/candidates/{candidate['id']}/promote",
            json={"severity": "Low"},
        ).status_code
        == 409
    )

    updated = app_client.patch(
        f"/api/engagements/{engagement_id}/findings/{finding['id']}",
        json={"severity": "Critical", "status": "Ready for Retest", "remediation": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["severity"] == "Critical"
    assert [item["event_type"] for item in updated.json()["history"]] == [
        "candidate_promoted",
        "severity_changed",
        "status_changed",
    ]
    assert (
        app_client.get(f"/api/engagements/{engagement_id}/findings").json()[0]["display_id"]
        == "FW-001"
    )


def test_review_classification_and_operator_notes_are_redacted(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)
    candidate = create_candidate(app_client, engagement_id)["candidate"]

    reviewed = app_client.post(
        f"/api/engagements/{engagement_id}/candidates/{candidate['id']}/review",
        json={
            "decision": "False Positive",
            "note": "Authorization: Bearer synthetic-review-secret\nExpected shared resource.",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_decision"] == "False Positive"
    assert "synthetic-review-secret" not in reviewed.text
    detail = app_client.get(f"/api/engagements/{engagement_id}/candidates/{candidate['id']}").json()
    assert detail["operator_notes"][0]["body"].startswith("Authorization: [REDACTED]")

    note = app_client.post(
        f"/api/engagements/{engagement_id}/notes",
        json={
            "target_type": "candidate",
            "target_id": candidate["id"],
            "body": "token=synthetic-note-secret",
        },
    )
    assert note.status_code == 201
    assert note.json()["body"] == f"token={REDACTED}"


def test_evidence_is_redacted_immutable_and_engagement_scoped(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    other_engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)
    raw = (
        "POST /api/profile HTTP/1.1\r\n"
        "Host: app.test\r\n"
        "Authorization: Bearer synthetic-request-secret\r\n"
        "Content-Type: application/json\r\n\r\n"
        '{"name":"Ada","password":"synthetic-body-secret"}'
    )
    exchange = app_client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={"base_url": "http://app.test", "raw": raw},
    ).json()

    created = app_client.post(
        f"/api/engagements/{engagement_id}/evidence",
        json={
            "evidence_type": "HTTP Request/Response",
            "title": "Original profile request",
            "source_exchange_id": exchange["id"],
        },
    )
    assert created.status_code == 201
    evidence = created.json()
    assert evidence["display_id"] == "EV-001"
    assert "synthetic-request-secret" not in created.text
    assert "synthetic-body-secret" not in created.text
    original_snapshot = evidence["snapshot"]

    with app_client.app.state.session_factory() as session:
        source = session.get(HttpExchange, exchange["id"])
        assert source is not None
        source.request_body = '{"name":"Changed"}'
        session.commit()
    unchanged = app_client.get(f"/api/engagements/{engagement_id}/evidence/{evidence['id']}").json()
    assert unchanged["snapshot"] == original_snapshot

    with app_client.app.state.session_factory() as session:
        source = session.get(HttpExchange, exchange["id"])
        assert source is not None
        session.delete(source)
        session.commit()
        stored = session.scalar(select(Evidence).where(Evidence.id == evidence["id"]))
        assert stored is not None
        assert stored.source_exchange_id is None
        assert stored.snapshot == original_snapshot

    wrong_scope = app_client.get(
        f"/api/engagements/{other_engagement_id}/evidence/{evidence['id']}"
    )
    assert wrong_scope.status_code == 404
    second = app_client.post(
        f"/api/engagements/{engagement_id}/evidence",
        json={"evidence_type": "Text Excerpt", "title": "Observation", "text": "Safe text"},
    )
    assert second.json()["display_id"] == "EV-002"


def test_multiple_retests_latest_summary_and_retest_evidence(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"order": {"id": 17, "total": 1250}})

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize(client, engagement_id)
        comparison = create_candidate(client, engagement_id)
        finding = client.post(
            f"/api/engagements/{engagement_id}/candidates/{comparison['candidate']['id']}/promote",
            json={"severity": "High"},
        ).json()
        original_evidence = client.post(
            f"/api/engagements/{engagement_id}/evidence",
            json={
                "evidence_type": "Response Comparison",
                "title": "Original comparison",
                "source_comparison_id": comparison["id"],
                "finding_id": finding["id"],
            },
        ).json()
        first = client.post(
            f"/api/engagements/{engagement_id}/findings/{finding['id']}/retests",
            json={
                "status": "Still Vulnerable",
                "operator_notes": "First retest",
                "evidence_ids": [original_evidence["id"]],
            },
        )
        second_evidence = client.post(
            f"/api/engagements/{engagement_id}/evidence",
            json={
                "evidence_type": "Operator Note",
                "title": "Fixed behavior",
                "text": "The endpoint now returns 403.",
                "finding_id": finding["id"],
            },
        ).json()
        second = client.post(
            f"/api/engagements/{engagement_id}/findings/{finding['id']}/retests",
            json={"status": "Fixed", "evidence_ids": [second_evidence["id"]]},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["display_id"] == "RT-001"
        assert second.json()["display_id"] == "RT-002"
        finding_id = finding["id"]

    with make_client() as restarted:
        persisted = restarted.get(f"/api/engagements/{engagement_id}/findings/{finding_id}").json()
        retests = restarted.get(f"/api/engagements/{engagement_id}/retests").json()

    assert persisted["latest_retest"]["display_id"] == "RT-002"
    assert persisted["latest_retest"]["status"] == "Fixed"
    assert persisted["status"] == "Fixed"
    assert [item["display_id"] for item in retests] == ["RT-002", "RT-001"]
    assert retests[0]["evidence_ids"] == [second_evidence["id"]]
    assert {item["event_type"] for item in persisted["history"]} >= {
        "candidate_promoted",
        "retest_added",
    }
