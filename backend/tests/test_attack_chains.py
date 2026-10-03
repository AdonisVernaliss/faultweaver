from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from faultweaver.findings.models import Evidence, Finding
from tests.test_engagements_and_scope import create_engagement


def seed_findings(client: TestClient, engagement_id: str, count: int = 3) -> list[Finding]:
    severities = ["High", "Medium", "Low"]
    with client.app.state.session_factory() as session:
        findings = [
            Finding(
                engagement_id=engagement_id,
                display_id=f"FW-{index:03d}",
                sequence_number=index,
                title=f"Synthetic finding {index}",
                category="authorization",
                severity=severities[index - 1],
                status="Open",
                affected_asset="app.test",
            )
            for index in range(1, count + 1)
        ]
        session.add_all(findings)
        session.commit()
        return findings


def seed_evidence(client: TestClient, engagement_id: str, number: int = 1) -> Evidence:
    with client.app.state.session_factory() as session:
        evidence = Evidence(
            engagement_id=engagement_id,
            display_id=f"EV-{number:03d}",
            sequence_number=number,
            evidence_type="Operator Note",
            title=f"Synthetic evidence {number}",
            snapshot={"text": "Redacted synthetic observation"},
        )
        session.add(evidence)
        session.commit()
        return evidence


def create_chain(client: TestClient, engagement_id: str, title: str = "Account path") -> dict:
    response = client.post(
        f"/api/engagements/{engagement_id}/attack-chains",
        json={"title": title, "description": "Operator-authored path"},
    )
    assert response.status_code == 201
    return response.json()


def add_finding_step(
    client: TestClient,
    engagement_id: str,
    chain_id: str,
    finding_id: str,
    position: int | None = None,
) -> dict:
    payload: dict[str, object] = {"step_type": "Finding", "finding_id": finding_id}
    if position is not None:
        payload["position"] = position
    response = client.post(
        f"/api/engagements/{engagement_id}/attack-chains/{chain_id}/steps", json=payload
    )
    assert response.status_code == 201
    return response.json()


def test_attack_chain_ids_are_stable_and_engagement_scoped(app_client: TestClient) -> None:
    first_engagement = create_engagement(app_client)
    second_engagement = create_engagement(app_client)

    first = create_chain(app_client, first_engagement)
    second = create_chain(app_client, first_engagement, "Second path")
    other = create_chain(app_client, second_engagement, "Other engagement path")
    renamed = app_client.patch(
        f"/api/engagements/{first_engagement}/attack-chains/{first['id']}",
        json={"title": "Renamed account path"},
    )

    assert first["display_id"] == "AC-001"
    assert second["display_id"] == "AC-002"
    assert other["display_id"] == "AC-001"
    assert renamed.status_code == 200
    assert renamed.json()["display_id"] == "AC-001"
    assert (
        app_client.get(
            f"/api/engagements/{second_engagement}/attack-chains/{first['id']}"
        ).status_code
        == 404
    )


def test_ordered_steps_removal_multiple_chains_and_finding_backlinks(
    app_client: TestClient,
) -> None:
    engagement_id = create_engagement(app_client)
    findings = seed_findings(app_client, engagement_id)
    first_chain = create_chain(app_client, engagement_id)
    second_chain = create_chain(app_client, engagement_id, "Administrative path")

    first_chain = add_finding_step(app_client, engagement_id, first_chain["id"], findings[0].id)
    intermediate = app_client.post(
        f"/api/engagements/{engagement_id}/attack-chains/{first_chain['id']}/steps",
        json={
            "step_type": "Intermediate",
            "title": "Authenticated session obtained",
            "description": "Operator verified the synthetic transition.",
        },
    )
    assert intermediate.status_code == 201
    first_chain = add_finding_step(
        app_client, engagement_id, first_chain["id"], findings[1].id, position=2
    )
    assert [step["position"] for step in first_chain["steps"]] == [1, 2, 3]
    assert [step["step_type"] for step in first_chain["steps"]] == [
        "Finding",
        "Finding",
        "Intermediate",
    ]

    reordered_ids = [step["id"] for step in reversed(first_chain["steps"])]
    reordered = app_client.put(
        f"/api/engagements/{engagement_id}/attack-chains/{first_chain['id']}/steps/order",
        json={"ordered_step_ids": reordered_ids},
    )
    assert reordered.status_code == 200
    assert [step["id"] for step in reordered.json()["steps"]] == reordered_ids
    assert reordered.json()["display_id"] == "AC-001"

    second_chain = add_finding_step(app_client, engagement_id, second_chain["id"], findings[0].id)
    backlink = app_client.get(f"/api/engagements/{engagement_id}/findings/{findings[0].id}").json()[
        "attack_chains"
    ]
    assert [item["display_id"] for item in backlink] == ["AC-001", "AC-002"]

    intermediate_step = next(
        step for step in reordered.json()["steps"] if step["step_type"] == "Intermediate"
    )
    removed = app_client.delete(
        f"/api/engagements/{engagement_id}/attack-chains/"
        f"{first_chain['id']}/steps/{intermediate_step['id']}"
    )
    assert removed.status_code == 200
    assert [step["position"] for step in removed.json()["steps"]] == [1, 2]
    history_types = [item["event_type"] for item in removed.json()["history"]]
    assert "steps_reordered" in history_types
    assert "step_removed" in history_types
    assert second_chain["steps"][0]["finding_id"] == findings[0].id


def test_chain_and_step_evidence_enforce_engagement_isolation(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    other_engagement = create_engagement(app_client)
    finding = seed_findings(app_client, engagement_id, 1)[0]
    other_finding = seed_findings(app_client, other_engagement, 1)[0]
    evidence = seed_evidence(app_client, engagement_id)
    other_evidence = seed_evidence(app_client, other_engagement)
    chain = create_chain(app_client, engagement_id)
    chain = add_finding_step(app_client, engagement_id, chain["id"], finding.id)
    step_id = chain["steps"][0]["id"]

    chain_link = app_client.post(
        f"/api/engagements/{engagement_id}/attack-chains/{chain['id']}/evidence",
        json={"evidence_id": evidence.id},
    )
    step_link = app_client.post(
        f"/api/engagements/{engagement_id}/attack-chains/{chain['id']}/steps/{step_id}/evidence",
        json={"evidence_id": evidence.id},
    )
    wrong_finding = app_client.post(
        f"/api/engagements/{engagement_id}/attack-chains/{chain['id']}/steps",
        json={"step_type": "Finding", "finding_id": other_finding.id},
    )
    wrong_evidence = app_client.post(
        f"/api/engagements/{engagement_id}/attack-chains/{chain['id']}/evidence",
        json={"evidence_id": other_evidence.id},
    )

    assert chain_link.status_code == 200
    assert [item["display_id"] for item in chain_link.json()["evidence"]] == ["EV-001"]
    assert step_link.status_code == 200
    assert step_link.json()["steps"][0]["evidence"][0]["display_id"] == "EV-001"
    assert wrong_finding.status_code == 404
    assert wrong_evidence.status_code == 404
    assert "evidence_attached" in {item["event_type"] for item in step_link.json()["history"]}


def test_validation_archive_history_and_restart_persistence(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    with make_client() as client:
        engagement_id = create_engagement(client)
        findings = seed_findings(client, engagement_id, 2)
        chain = create_chain(client, engagement_id, "Cross-tenant account compromise")
        invalid = client.patch(
            f"/api/engagements/{engagement_id}/attack-chains/{chain['id']}",
            json={"status": "Validated"},
        )
        assert invalid.status_code == 422
        chain = add_finding_step(client, engagement_id, chain["id"], findings[0].id)
        still_invalid = client.patch(
            f"/api/engagements/{engagement_id}/attack-chains/{chain['id']}",
            json={"status": "Validated"},
        )
        assert still_invalid.status_code == 422
        chain = add_finding_step(client, engagement_id, chain["id"], findings[1].id)
        validated = client.patch(
            f"/api/engagements/{engagement_id}/attack-chains/{chain['id']}",
            json={
                "resulting_impact": "A tenant can combine both issues to access restricted data.",
                "status": "Validated",
            },
        )
        assert validated.status_code == 200
        assert validated.json()["status"] == "Validated"
        chain_id = chain["id"]
        ordered_ids = [step["id"] for step in validated.json()["steps"]]

    with make_client() as restarted:
        persisted = restarted.get(f"/api/engagements/{engagement_id}/attack-chains/{chain_id}")
        assert persisted.status_code == 200
        assert persisted.json()["status"] == "Validated"
        assert [step["id"] for step in persisted.json()["steps"]] == ordered_ids
        archived = restarted.delete(f"/api/engagements/{engagement_id}/attack-chains/{chain_id}")
        active = restarted.get(f"/api/engagements/{engagement_id}/attack-chains")
        archived_list = restarted.get(
            f"/api/engagements/{engagement_id}/attack-chains?status=Archived"
        )
        retained = restarted.get(f"/api/engagements/{engagement_id}/attack-chains/{chain_id}")
        rejected_mutation = restarted.post(
            f"/api/engagements/{engagement_id}/attack-chains/{chain_id}/steps",
            json={"step_type": "Intermediate", "title": "Should not be added"},
        )

    assert archived.status_code == 204
    assert active.json() == []
    assert archived_list.json()[0]["display_id"] == "AC-001"
    assert retained.json()["status"] == "Archived"
    assert retained.json()["history"][-1]["event_type"] == "attack_chain_archived"
    assert rejected_mutation.status_code == 409
