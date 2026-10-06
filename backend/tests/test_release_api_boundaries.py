import pytest

from tests.test_engagements_and_scope import create_engagement
from tests.test_http_import import authorize
from tests.test_replay_and_persistence import import_request


def test_note_evidence_rejects_foreign_optional_request_reference(app_client):
    first = create_engagement(app_client)
    other = create_engagement(app_client)
    authorize(app_client, other)
    foreign = import_request(app_client, other)
    response = app_client.post(
        f"/api/engagements/{first}/evidence",
        json={
            "evidence_type": "Operator Note",
            "title": "Synthetic note",
            "text": "Local observation",
            "source_exchange_id": foreign,
        },
    )
    assert response.status_code == 404
    assert app_client.get(f"/api/engagements/{first}/evidence").json() == []


def test_api_sensitive_responses_are_not_cacheable(app_client):
    for path in ("/api/engagements", "/api/requests/missing"):
        response = app_client.get(path)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize(
    "origin", ["http://*.example.test", "http://*", "http://local\nhost", "http://localhost:0"]
)
def test_ambiguous_cors_configuration_is_rejected(monkeypatch, origin):
    from faultweaver.config import Settings
    from faultweaver.storage.keys import StorageError

    monkeypatch.setenv("FAULTWEAVER_ALLOWED_ORIGINS", origin)
    with pytest.raises(StorageError):
        Settings.from_environment()
