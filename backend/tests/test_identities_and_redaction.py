import logging

from fastapi.testclient import TestClient
from sqlalchemy import select

from faultweaver.identities.models import Identity
from faultweaver.redaction import (
    REDACTED,
    SecretRedactingFilter,
    is_sensitive_key,
    redact_body,
    redact_url,
)
from tests.test_engagements_and_scope import create_engagement
from tests.test_http_import import authorize


def test_identity_crud_is_scoped_and_credentials_are_redacted(app_client: TestClient) -> None:
    first_engagement = create_engagement(app_client)
    second_engagement = create_engagement(app_client)

    anonymous = app_client.get(f"/api/engagements/{first_engagement}/identities").json()
    assert len(anonymous) == 1
    assert anonymous[0]["name"] == "Anonymous"
    assert anonymous[0]["is_anonymous"] is True

    payload = {
        "name": "Tenant A operator",
        "description": "Synthetic local identity",
        "bearer_token": "synthetic-bearer-secret",
        "api_key_header": "X-API-Key",
        "api_key_value": "synthetic-api-secret",
        "cookies": [{"name": "session", "value": "synthetic-cookie-secret"}],
        "custom_headers": [
            {"name": "X-Tenant", "value": "tenant-a"},
            {"name": "X-Api-Key-Secondary", "value": "synthetic-secondary-secret"},
        ],
    }
    created = app_client.post(f"/api/engagements/{first_engagement}/identities", json=payload)

    assert created.status_code == 201
    identity = created.json()
    assert identity["bearer_token"] == REDACTED
    assert identity["api_key_value"] == REDACTED
    assert identity["cookies"][0]["value"] == REDACTED
    assert identity["custom_headers"] == [
        {"name": "X-Tenant", "value": "tenant-a"},
        {"name": "X-Api-Key-Secondary", "value": REDACTED},
    ]

    duplicate_other_engagement = app_client.post(
        f"/api/engagements/{second_engagement}/identities", json=payload
    )
    duplicate_same_engagement = app_client.post(
        f"/api/engagements/{first_engagement}/identities", json=payload
    )
    assert duplicate_other_engagement.status_code == 201
    assert duplicate_same_engagement.status_code == 409

    updated = app_client.patch(
        f"/api/engagements/{first_engagement}/identities/{identity['id']}",
        json={"name": "Tenant A reviewer", "description": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Tenant A reviewer"
    assert updated.json()["bearer_token"] == REDACTED

    with app_client.app.state.session_factory() as session:
        stored = session.scalar(select(Identity).where(Identity.id == identity["id"]))
        assert stored is not None
        assert stored.bearer_token == "synthetic-bearer-secret"
        assert stored.api_key_value == "synthetic-api-secret"

    wrong_scope = app_client.get(
        f"/api/engagements/{second_engagement}/identities/{identity['id']}"
    )
    assert wrong_scope.status_code == 404
    assert (
        app_client.delete(
            f"/api/engagements/{first_engagement}/identities/{anonymous[0]['id']}"
        ).status_code
        == 409
    )
    assert (
        app_client.delete(
            f"/api/engagements/{first_engagement}/identities/{identity['id']}"
        ).status_code
        == 204
    )


def test_exchange_api_redacts_headers_and_structured_body(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)
    raw = (
        "POST /api/login HTTP/1.1\r\n"
        "Host: app.test\r\n"
        "Authorization: Bearer synthetic-auth-secret\r\n"
        "Cookie: session=synthetic-cookie-secret\r\n"
        "X-API-Key: synthetic-api-secret\r\n"
        "Content-Type: application/json\r\n\r\n"
        '{"username":"synthetic-user","password":"synthetic-password","nested":'
        '{"access_token":"synthetic-token"}}'
    )

    imported = app_client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={"base_url": "http://app.test", "raw": raw},
    )

    assert imported.status_code == 201
    public = imported.json()
    header_values = {item["name"].lower(): item["value"] for item in public["request_headers"]}
    assert header_values["authorization"] == REDACTED
    assert header_values["cookie"] == REDACTED
    assert header_values["x-api-key"] == REDACTED
    assert public["request_body"] == (
        '{"username":"synthetic-user","password":"[REDACTED]",'
        '"nested":{"access_token":"[REDACTED]"}}'
    )
    detail = app_client.get(f"/api/requests/{public['id']}").json()
    assert "synthetic-auth-secret" not in detail["raw_request"]
    assert "synthetic-password" not in detail["raw_request"]


def test_logging_filter_redacts_structured_secrets() -> None:
    record = logging.LogRecord(
        "faultweaver.test",
        logging.INFO,
        __file__,
        1,
        {"password": "synthetic-password", "safe": "visible"},
        (),
        None,
    )

    assert SecretRedactingFilter().filter(record) is True
    assert record.msg == {"password": REDACTED, "safe": "visible"}


def test_free_text_redacts_inline_authorization_and_named_secrets() -> None:
    text = (
        "HTTP 403 observed. Authorization: Bearer synthetic-inline-secret; "
        "token: synthetic-token-value"
    )

    redacted = redact_body(text)

    assert redacted == "HTTP 403 observed. Authorization: [REDACTED]; token: [REDACTED]"


def test_urlencoded_body_redacts_prefixed_sensitive_fields() -> None:
    body = (
        "username=synthetic-user&password=synthetic-password&"
        "matchingPassword=synthetic-confirm&passwordConfirmation=synthetic-copy&"
        "user_token=synthetic-csrf&access_token=synthetic-access&safe=visible"
    )

    redacted = redact_body(body)

    assert redacted == (
        "username=synthetic-user&password=[REDACTED]&matchingPassword=[REDACTED]&"
        "passwordConfirmation=[REDACTED]&user_token=[REDACTED]&"
        "access_token=[REDACTED]&safe=visible"
    )


def test_sensitive_key_normalizes_password_components_without_broadening_others() -> None:
    assert is_sensitive_key("matchingPassword")
    assert is_sensitive_key("passwordConfirmation")
    assert not is_sensitive_key("authorizationMatrix")
    assert not is_sensitive_key("tokenType")


def test_urls_redact_query_fragment_and_userinfo_credentials() -> None:
    redacted = redact_url(
        "https://synthetic-user:synthetic-password@api.example.test:8443/api/items"
        "?page=2&access_token=synthetic-query-secret#token=synthetic-fragment-secret"
    )

    assert "synthetic-user" not in redacted
    assert "synthetic-password" not in redacted
    assert "synthetic-query-secret" not in redacted
    assert "synthetic-fragment-secret" not in redacted
    assert "api.example.test:8443/api/items?page=2" in redacted
    assert redacted.count("%5BREDACTED%5D") == 3


def test_validation_errors_do_not_echo_identity_secrets(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)

    response = app_client.post(
        f"/api/engagements/{engagement_id}/identities",
        json={
            "name": "Invalid synthetic identity",
            "bearer_token": "synthetic-validation-secret",
            "api_key_header": "X-API-Key",
        },
    )

    assert response.status_code == 422
    assert "synthetic-validation-secret" not in response.text
    assert REDACTED in response.text
