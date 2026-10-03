import json
from pathlib import Path

import pytest

from faultweaver.imports.canonical import ParserLimits
from faultweaver.imports.curl import CurlParseError, parse_curl
from faultweaver.imports.har import HarParseError, parse_har
from faultweaver.imports.openapi import OpenApiParseError, parse_openapi

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def limits() -> ParserLimits:
    return ParserLimits(
        max_document_bytes=20_000,
        max_entries=10,
        max_request_body_bytes=16,
        max_response_body_bytes=16,
    )


def test_har_parses_headers_cookies_bodies_response_and_timing(limits: ParserLimits) -> None:
    content = (FIXTURES / "sample.har").read_text()

    result = parse_har(content, limits)
    record = result.records[0]

    assert result.total_records == 1
    assert record.method == "POST"
    assert record.request_body == '{"ok":true}'
    assert record.response_body == '{"ok":true}'
    assert record.response_elapsed_ms == 12.5
    assert record.redirect_chain == ["https://example.test/api/orders/18"]
    assert [item for item in record.request_headers if item["name"] == "X-Trace"] == [
        {"name": "X-Trace", "value": "one"},
        {"name": "X-Trace", "value": "two"},
    ]
    assert any(item["name"] == "Cookie" for item in record.request_headers)
    assert any(item["name"] == "Set-Cookie" for item in record.response_headers)


def test_har_partial_failure_limits_and_binary_behavior(limits: ParserLimits) -> None:
    result = parse_har(
        json.dumps(
            {
                "log": {
                    "entries": [
                        {"request": {"method": "GET", "url": "https://example.test/17"}},
                        {"request": {"method": "GET"}},
                        {
                            "request": {
                                "method": "POST",
                                "url": "https://example.test/18",
                                "postData": {"text": "x" * 20},
                            },
                            "response": {
                                "status": 200,
                                "content": {"text": "@@not-base64@@", "encoding": "base64"},
                            },
                        },
                        {
                            "request": {"method": "GET", "url": "https://example.test/19"},
                            "response": {
                                "status": 200,
                                "content": {"text": "/wAB", "encoding": "base64"},
                            },
                        },
                    ]
                }
            }
        ),
        limits,
    )

    assert len(result.records) == 3
    assert result.skipped_count == 1
    assert result.records[1].request_body == "x" * 16
    assert result.records[1].response_body is None
    assert result.records[2].response_body.startswith("[binary content omitted")
    assert any("invalid base64" in warning for warning in result.warnings)
    assert any("request body was truncated" in warning for warning in result.warnings)

    with pytest.raises(HarParseError, match="valid JSON"):
        parse_har("{", limits)
    with pytest.raises(HarParseError, match="log object"):
        parse_har("{}", limits)
    with pytest.raises(HarParseError, match="byte limit"):
        parse_har("x" * 20_001, limits)
    with pytest.raises(HarParseError, match="more than 10 entries"):
        parse_har(json.dumps({"log": {"entries": [{}] * 11}}), limits)


def test_curl_parses_devtools_subset_without_execution(limits: ParserLimits) -> None:
    result = parse_curl(
        """curl 'https://example.test/api/orders/17' \\
          -X POST \\
          -H 'X-Trace: one' -H 'X-Trace: two' \\
          -b 'sid=synthetic' --json '{"state":"open"}' --compressed""",
        limits,
    )
    record = result.records[0]

    assert record.method == "POST"
    assert record.request_body == '{"state":"open"}'
    assert [item for item in record.request_headers if item["name"] == "X-Trace"] == [
        {"name": "X-Trace", "value": "one"},
        {"name": "X-Trace", "value": "two"},
    ]
    assert any(item["name"] == "Cookie" for item in record.request_headers)
    assert any(item["value"] == "application/json" for item in record.request_headers)
    assert result.warnings == ["Transport option --compressed was ignored"]


def test_curl_get_body_variants_and_shell_syntax_are_safe(limits: ParserLimits) -> None:
    get_record = parse_curl(
        "curl https://example.test/search?existing=yes -G --data 'q=two words'", limits
    ).records[0]
    binary_record = parse_curl(
        "curl https://example.test/upload --data-binary 'literal;data'", limits
    ).records[0]

    assert get_record.method == "GET"
    assert "existing=yes" in get_record.url and "q=two+words" in get_record.url
    assert get_record.request_body is None
    assert binary_record.request_body == "literal;data"
    assert parse_curl("curl 'https://example.test/a;b'", limits).records[0].url.endswith("a;b")

    with pytest.raises(CurlParseError, match="command substitution"):
        parse_curl("curl 'https://example.test/$(touch synthetic-marker)'", limits)
    with pytest.raises(CurlParseError, match="malformed quoting"):
        parse_curl("curl 'https://example.test", limits)
    with pytest.raises(CurlParseError, match="Unsupported cURL option"):
        parse_curl("curl --form a=b https://example.test", limits)
    with pytest.raises(CurlParseError, match="File-backed"):
        parse_curl("curl --data-binary @/private/file https://example.test", limits)
    with pytest.raises(CurlParseError, match="Exactly one"):
        parse_curl("curl https://example.test --output out.txt touch", limits)


def test_openapi_json_yaml_refs_security_and_no_remote_fetch(limits: ParserLimits) -> None:
    result = parse_openapi((FIXTURES / "sample-openapi.json").read_text(), limits)
    endpoint = result.endpoints[0]

    assert endpoint.server_url == "https://api.example.test/v1"
    assert endpoint.details["operation_id"] == "getUser"
    assert endpoint.details["parameters"][0]["name"] == "id"
    assert endpoint.details["security"][0]["kind"] == "Bearer"
    assert any("external reference" in warning for warning in result.warnings)

    yaml_result = parse_openapi((FIXTURES / "sample-openapi.yaml").read_text(), limits)
    assert yaml_result.endpoints[0].path_template == "/health"


def test_openapi_rejects_unsafe_or_invalid_documents(limits: ParserLimits) -> None:
    with pytest.raises(OpenApiParseError, match="safe YAML"):
        parse_openapi("!!python/object/apply:os.system ['touch synthetic-marker']", limits)
    with pytest.raises(OpenApiParseError, match="OpenAPI 3.0 or 3.1"):
        parse_openapi('{"swagger":"2.0","paths":{}}', limits)
    with pytest.raises(OpenApiParseError, match="paths object"):
        parse_openapi('{"openapi":"3.1.0"}', limits)
    with pytest.raises(OpenApiParseError, match="byte limit"):
        parse_openapi("x" * 20_001, limits)

    result = parse_openapi(
        '{"openapi":"3.1.0","servers":[{"url":"file:///private"}],'
        '"paths":{"not-a-path":{"get":{}},"/ok":{"get":{"responses":{}}}}}',
        limits,
    )
    assert len(result.endpoints) == 1
    assert result.endpoints[0].server_url is None
    assert result.skipped_count == 1
    assert any("invalid server URL" in warning for warning in result.warnings)
