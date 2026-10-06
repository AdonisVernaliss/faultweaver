from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import event

from faultweaver.http_traffic.models import HttpExchange
from tests.test_engagements_and_scope import create_engagement


def authorize(client: TestClient, engagement_id: str) -> None:
    response = client.post(
        f"/api/engagements/{engagement_id}/scopes",
        json={"scheme": "http", "hostname": "app.test", "port": 80, "path_prefix": "/api"},
    )
    assert response.status_code == 201


def test_raw_http_import_and_request_listing(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)
    raw = (
        "POST /api/projects?state=open HTTP/1.1\r\n"
        "Host: app.test\r\n"
        "Content-Type: application/json\r\n"
        "X-Trace: first\r\n"
        "X-Trace: second\r\n\r\n"
        '{"name":"Synthetic"}'
    )

    response = app_client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={"base_url": "http://app.test", "raw": raw},
    )

    assert response.status_code == 201
    imported = response.json()
    assert imported["method"] == "POST"
    assert imported["url"] == "http://app.test/api/projects?state=open"
    assert imported["path"] == "/api/projects"
    assert imported["query"] == "state=open"
    assert imported["source"] == "raw_import"
    assert imported["request_body"] == '{"name":"Synthetic"}'
    assert [header for header in imported["request_headers"] if header["name"] == "X-Trace"] == [
        {"name": "X-Trace", "value": "first"},
        {"name": "X-Trace", "value": "second"},
    ]

    listing = app_client.get(f"/api/engagements/{engagement_id}/requests", params={"q": "projects"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == imported["id"]

    detail = app_client.get(f"/api/requests/{imported['id']}")
    assert detail.status_code == 200
    assert detail.json()["raw_request"].startswith("POST /api/projects?state=open HTTP/1.1")


def test_import_rejects_out_of_scope_and_malformed_requests(app_client: TestClient) -> None:
    engagement_id = create_engagement(app_client)
    authorize(app_client, engagement_id)

    out_of_scope = app_client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={
            "base_url": "http://other.test",
            "raw": "GET /api/users HTTP/1.1\r\nHost: other.test\r\n\r\n",
        },
    )
    malformed = app_client.post(
        f"/api/engagements/{engagement_id}/traffic/raw",
        json={"base_url": "http://app.test", "raw": "not-http"},
    )

    assert out_of_scope.status_code == 403
    assert malformed.status_code == 422


def test_request_listing_never_materializes_payload_columns(app_client: TestClient) -> None:
    engagement = create_engagement(app_client)
    authorize(app_client, engagement)
    imported = app_client.post(
        f"/api/engagements/{engagement}/traffic/raw",
        json={
            "base_url": "http://app.test",
            "raw": (
                "POST /api/items?token=synthetic-list-token HTTP/1.1\r\n"
                "Host: app.test\r\n\r\nlarge-private-payload"
            ),
        },
    ).json()
    statements = []
    engine = app_client.app.state.session_factory.kw["bind"]

    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        page = app_client.get(f"/api/engagements/{engagement}/requests").json()
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    for field in (
        "request_body",
        "request_headers",
        "response_body",
        "response_headers",
        "redirect_chain",
        "crawl_error",
    ):
        assert field not in page["items"][0]
        assert all(f"http_exchanges.{field}" not in statement for statement in statements)
    assert "synthetic-list-token" not in str(page)
    assert (
        app_client.get(f"/api/requests/{imported['id']}").json()["request_body"]
        == "large-private-payload"
    )


def test_workspace_lists_do_not_materialize_http_or_evidence_payloads(app_client: TestClient):
    from tests.test_finding_lifecycle import create_candidate

    engagement = create_engagement(app_client)
    authorize(app_client, engagement)
    comparison = create_candidate(app_client, engagement)
    prefix = f"/api/engagements/{engagement}"
    saved = app_client.post(
        prefix + "/evidence",
        json={
            "evidence_type": "Response Comparison",
            "title": "List boundary",
            "source_comparison_id": comparison["id"],
        },
    ).json()
    finding = app_client.post(
        prefix + "/candidates/" + comparison["candidate"]["id"] + "/promote",
        json={"severity": "High"},
    ).json()
    chain = app_client.post(prefix + "/attack-chains", json={"title": "Metadata boundary"}).json()
    app_client.post(
        prefix + "/attack-chains/" + chain["id"] + "/steps",
        json={"step_type": "Finding", "finding_id": finding["id"]},
    )
    app_client.post(
        prefix + "/attack-chains/" + chain["id"] + "/evidence", json={"evidence_id": saved["id"]}
    )
    statements = []
    engine = app_client.app.state.session_factory.kw["bind"]

    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        for endpoint in (
            "requests",
            "authorization-matrix",
            "candidates",
            "evidence",
            "findings",
            "retests",
            "attack-chains",
        ):
            response = app_client.get(prefix + "/" + endpoint)
            assert response.status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    for field in (
        "http_exchanges.request_body",
        "http_exchanges.response_body",
        "http_exchanges.request_headers",
        "http_exchanges.response_headers",
        "response_comparisons.result",
        "evidence.snapshot",
        "identities.bearer_token",
    ):
        assert all(field not in statement for statement in statements), field
    assert "snapshot" not in app_client.get(prefix + "/evidence").json()[0]
    assert "original" not in app_client.get(prefix + "/candidates").json()[0]
    assert app_client.get(prefix + "/evidence/" + saved["id"]).json() == {
        **saved,
        "finding_id": finding["id"],
    }
    detail = app_client.get(prefix + "/candidates/" + comparison["candidate"]["id"]).json()
    assert detail["original"] and detail["supporting_replays"] and detail["comparison_result"]


def test_request_search_spans_pages_and_matches_literal_method_status_and_query(
    app_client: TestClient,
) -> None:
    engagement_id = create_engagement(app_client)
    with app_client.app.state.session_factory() as session:
        for index in range(105):
            session.add(
                HttpExchange(
                    engagement_id=engagement_id,
                    source="har",
                    method="GET",
                    url=f"http://app.test/api/items/{index}",
                    host="app.test",
                    path=f"/api/items/{index}",
                    response_status=200,
                )
            )
        session.add(
            HttpExchange(
                id="older-special",
                engagement_id=engagement_id,
                source="curl",
                method="POST",
                url="http://app.test/api/archive?note=100%25_done",
                host="app.test",
                path="/api/archive",
                query="note=100%25_done",
                response_status=418,
                created_at=datetime(2000, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()
    prefix = f"/api/engagements/{engagement_id}/requests"
    first = app_client.get(prefix).json()
    second = app_client.get(prefix, params={"offset": 100}).json()
    assert first["total"] == second["total"] == 106
    assert len(first["items"]) == 100
    assert len(second["items"]) == 6
    assert second["items"][-1]["id"] == "older-special"
    assert len({r["id"] for r in first["items"] + second["items"]}) == 106
    for query in ["post", "418", "%25_", "archive"]:
        result = app_client.get(prefix, params={"q": query}).json()
        assert [r["id"] for r in result["items"]] == ["older-special"]
    assert app_client.get(prefix, params={"q": "_"}).json()["total"] == 1
    assert app_client.get(prefix, params={"q": "post", "source": "har"}).json()["total"] == 0
    other = create_engagement(app_client)
    assert (
        app_client.get(f"/api/engagements/{other}/requests", params={"q": "418"}).json()["total"]
        == 0
    )
