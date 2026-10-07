import json

import httpx
import pytest

from faultweaver.analysis.normalization import normalize_response
from faultweaver.redaction import REDACTED
from tests.test_engagements_and_scope import create_engagement
from tests.test_http_import import authorize
from tests.test_replay_and_persistence import import_request


def test_custom_identity_headers_stay_secret_after_edit_and_original_replay(make_client):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"echo": request.headers.get("x-principal")})

    with make_client(httpx.MockTransport(handler)) as client:
        engagement = create_engagement(client)
        authorize(client, engagement)
        root = f"/api/engagements/{engagement}"
        created = client.post(
            f"{root}/identities",
            json={
                "name": "Custom authentication",
                "api_key_header": "X-Workspace",
                "api_key_value": "synthetic-workspace-secret",
                "custom_headers": [{"name": "X-Principal", "value": "synthetic-principal-secret"}],
            },
        )
        assert created.status_code == 201
        assert "synthetic-principal-secret" not in created.text
        identity = created.json()
        request_id = import_request(client, engagement)
        replay = client.post(
            f"/api/requests/{request_id}/replay", json={"identity_id": identity["id"]}
        )
        assert replay.status_code == 201
        assert "synthetic-workspace-secret" not in replay.text
        assert "synthetic-principal-secret" not in replay.text
        replay_id = replay.json()["id"]
        client.patch(
            f"{root}/identities/{identity['id']}",
            json={"custom_headers": [], "api_key_header": None, "api_key_value": None},
        ).raise_for_status()
        client.delete(f"{root}/identities/{identity['id']}").raise_for_status()
        for response in (
            client.get(f"/api/requests/{replay_id}"),
            client.post(f"/api/requests/{replay_id}/replay", json={}),
        ):
            response.raise_for_status()
            assert "synthetic-workspace-secret" not in response.text
            assert "synthetic-principal-secret" not in response.text
            assert REDACTED in response.text
    assert all(item.headers["x-workspace"] == "synthetic-workspace-secret" for item in seen)
    assert all(item.headers["x-principal"] == "synthetic-principal-secret" for item in seen)


def test_validation_error_never_returns_submitted_secret(app_client):
    engagement = create_engagement(app_client)
    response = app_client.post(
        f"/api/engagements/{engagement}/identities",
        json={"name": "Validation", "bearer_token": ["synthetic-invalid-secret"]},
    )
    assert response.status_code == 422
    assert "synthetic-invalid-secret" not in response.text
    assert "input" not in response.json()["detail"][0]


@pytest.mark.parametrize("action", ["replay", "compare"])
def test_unencodable_replay_header_is_a_safe_error(make_client, action):
    with make_client(httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        engagement = create_engagement(client)
        authorize(client, engagement)
        request_id = import_request(client, engagement)
        identity = client.post(
            f"/api/engagements/{engagement}/identities",
            json={
                "name": "Unencodable",
                "custom_headers": [{"name": "X-Principal", "value": "synthetic-secret-Ж"}],
            },
        ).json()
        anonymous = next(
            item
            for item in client.get(f"/api/engagements/{engagement}/identities").json()
            if item["is_anonymous"]
        )
        payload = (
            {"identity_id": identity["id"]}
            if action == "replay"
            else {"identity_a_id": identity["id"], "identity_b_id": anonymous["id"]}
        )
        response = client.post(f"/api/requests/{request_id}/{action}", json=payload)
        assert response.status_code == 502
        assert "synthetic-secret" not in response.text


def test_comparison_redacts_location_and_redirect_urls():
    result = normalize_response(
        status=302,
        headers=[{"name": "Location", "value": "/done?token=synthetic-location-secret"}],
        body="",
        redirect_chain=["http://app.test/done?token=synthetic-redirect-secret"],
    ).to_dict()
    encoded = json.dumps(result)
    assert "synthetic-location-secret" not in encoded
    assert "synthetic-redirect-secret" not in encoded


def test_legacy_identity_exchange_is_fail_closed_without_source_mutation(app_client):
    from faultweaver.http_traffic.models import HttpExchange

    engagement = create_engagement(app_client)
    authorize(app_client, engagement)
    request_id = import_request(app_client, engagement)
    with app_client.app.state.session_factory() as session:
        exchange = session.get(HttpExchange, request_id)
        exchange.auth_source = "identity"
        exchange.request_headers = [{"name": "X-Legacy", "value": "synthetic-legacy-secret"}]
        exchange.response_body = '{"echo":"synthetic-legacy-secret"}'
        session.commit()
    response = app_client.get(f"/api/requests/{request_id}")
    assert response.status_code == 200
    assert "synthetic-legacy-secret" not in response.text
    with app_client.app.state.session_factory() as session:
        assert "synthetic-legacy-secret" in session.get(HttpExchange, request_id).response_body
