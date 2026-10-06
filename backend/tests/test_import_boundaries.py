import json

import pytest

from faultweaver.imports.canonical import ParserLimits
from faultweaver.imports.har import parse_har
from faultweaver.imports.openapi import OpenApiParseError, parse_openapi

LIMITS = ParserLimits(100_000, 10, 1000, 1000)


@pytest.mark.parametrize(
    "content",
    [
        "openapi: 3.1.0\npaths: { /a: { 123: {} } }",
        "openapi: 3.1.0\npaths: &cycle { /a: {get: {summary: *cycle}} }",
        'openapi: 3.1.0\nservers: [{url: "http://[invalid"}]\npaths: {}',
        json.dumps({"openapi": "3.1.0", "paths": {"/a": {"get": {"summary": [[[[[]]]]]}}}}),
    ],
)
def test_malformed_openapi_is_rejected_or_safely_represented(content):
    try:
        result = parse_openapi(content, LIMITS)
    except OpenApiParseError:
        return
    assert len(result.endpoints) <= LIMITS.max_entries
    json.dumps([item.details for item in result.endpoints])


def test_openapi_server_expansion_has_total_record_limit():
    content = json.dumps(
        {
            "openapi": "3.1.0",
            "servers": [{"url": f"http://app.test:{8000 + index}"} for index in range(10)],
            "paths": {"/a": {"get": {}}, "/b": {"get": {}}},
        }
    )
    with pytest.raises(OpenApiParseError, match="limit|more than"):
        parse_openapi(content, LIMITS)


def test_yaml_integer_response_codes_remain_supported():
    result = parse_openapi(
        "openapi: 3.1.0\npaths: { /a: { get: { responses: { 200: {description: OK} } } } }",
        LIMITS,
    )
    assert "200" in result.endpoints[0].details["responses"]


def test_har_malformed_url_is_counted_and_nonfinite_timing_not_retained():
    result = parse_har(
        json.dumps(
            {
                "log": {
                    "entries": [
                        {"request": {"method": "GET", "url": "http://[invalid"}},
                        {"request": {"method": "GET", "url": "http://app.test/"}, "time": 1e309},
                    ]
                }
            }
        ),
        LIMITS,
    )
    assert result.skipped_count == 1
    assert len(result.records) == 1
    assert result.records[0].response_elapsed_ms is None
