from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from tests.test_engagements_and_scope import create_engagement
from tests.test_http_import import authorize
from tests.test_replay_and_persistence import import_request


def create_identity(client: TestClient, engagement_id: str, name: str, token: str) -> str:
    response = client.post(
        f"/api/engagements/{engagement_id}/identities",
        json={"name": name, "bearer_token": token},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_differential_replay_persists_explainable_candidate_and_matrix(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("authorization")
        request_id = (
            "87d95099-3f36-4df3-8c78-707755ea8490"
            if token == "Bearer synthetic-tenant-a"
            else "b13e9ed4-f49d-4dc8-8c7a-ffdb77a0b65f"
        )
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "etag": request_id},
            json={
                "order": {"id": 17, "total": 1250, "currency": "USD"},
                "request_id": request_id,
            },
        )

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize(client, engagement_id)
        request_id = import_request(client, engagement_id, "/api/orders/17")
        identity_a = create_identity(client, engagement_id, "Tenant A", "synthetic-tenant-a")
        identity_b = create_identity(client, engagement_id, "Tenant B", "synthetic-tenant-b")

        response = client.post(
            f"/api/requests/{request_id}/compare",
            json={"identity_a_id": identity_a, "identity_b_id": identity_b},
        )

        assert response.status_code == 201
        comparison = response.json()
        assert comparison["replay_a"]["identity_id"] == identity_a
        assert comparison["replay_b"]["identity_id"] == identity_b
        assert comparison["result"]["diff"]["normalized_similarity"] == 1.0
        assert comparison["result"]["diff"]["json"]["structural_similarity"] == 1.0
        candidate = comparison["candidate"]
        assert candidate["status"] == "candidate"
        assert candidate["confidence"] == "medium"
        assert candidate["comparison_id"] == comparison["id"]
        assert set(candidate["supporting_replay_ids"]) == {
            comparison["replay_a"]["id"],
            comparison["replay_b"]["id"],
        }
        assert any("manual authorization review" in item for item in candidate["reasoning"])

        matrix = client.get(f"/api/engagements/{engagement_id}/authorization-matrix").json()
        row = next(item for item in matrix["rows"] if item["path"] == "/api/orders/17")
        assert row["cells"][identity_a] == {
            "state": "observed",
            "status": 200,
            "evidence_request_id": comparison["replay_a"]["id"],
        }
        anonymous_id = next(item["id"] for item in matrix["identities"] if item["is_anonymous"])
        assert row["cells"][anonymous_id]["state"] == "not_tested"
        comparison_id = comparison["id"]
        candidate_id = candidate["id"]

    with make_client() as restarted:
        persisted = restarted.get(f"/api/comparisons/{comparison_id}")
        candidates = restarted.get(f"/api/engagements/{engagement_id}/candidates")
        updated = restarted.patch(
            f"/api/engagements/{engagement_id}/candidates/{candidate_id}",
            json={"status": "rejected", "notes": "Reviewed as expected tenant sharing."},
        )

    assert persisted.status_code == 200
    assert persisted.json()["candidate"]["id"] == candidate_id
    assert candidates.status_code == 200
    assert [item["id"] for item in candidates.json()] == [candidate_id]
    assert updated.status_code == 200
    assert updated.json()["status"] == "rejected"


def test_dissimilar_or_unsuccessful_identity_result_does_not_create_candidate(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") == "Bearer synthetic-allowed":
            return httpx.Response(200, json={"order": {"id": 17, "total": 1250}})
        return httpx.Response(403, json={"detail": "forbidden"})

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize(client, engagement_id)
        request_id = import_request(client, engagement_id, "/api/orders/17")
        allowed = create_identity(client, engagement_id, "Allowed", "synthetic-allowed")
        denied = create_identity(client, engagement_id, "Denied", "synthetic-denied")

        comparison = client.post(
            f"/api/requests/{request_id}/compare",
            json={"identity_a_id": allowed, "identity_b_id": denied},
        )

    assert comparison.status_code == 201
    assert comparison.json()["candidate"] is None
    assert comparison.json()["result"]["diff"]["status"]["changed"] is True


def test_differential_replay_keeps_redirects_inside_authorized_scope(
    make_client: Callable[[httpx.MockTransport | None], TestClient],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") == "Bearer synthetic-second":
            return httpx.Response(302, headers={"location": "http://outside.test/private"})
        return httpx.Response(200, json={"ok": True})

    with make_client(httpx.MockTransport(handler)) as client:
        engagement_id = create_engagement(client)
        authorize(client, engagement_id)
        request_id = import_request(client, engagement_id, "/api/orders/17")
        first = create_identity(client, engagement_id, "First", "synthetic-first")
        second = create_identity(client, engagement_id, "Second", "synthetic-second")

        response = client.post(
            f"/api/requests/{request_id}/compare",
            json={"identity_a_id": first, "identity_b_id": second},
        )
        requests = client.get(f"/api/engagements/{engagement_id}/requests").json()

    assert response.status_code == 403
    assert requests["total"] == 1
