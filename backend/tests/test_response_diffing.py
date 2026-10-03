from faultweaver.analysis.diffing import compare_responses
from faultweaver.analysis.normalization import normalize_response


def normalized(
    body: str | None,
    *,
    status: int = 200,
    content_type: str = "application/json",
    headers: list[dict[str, str]] | None = None,
    redirects: list[str] | None = None,
):
    return normalize_response(
        status=status,
        headers=[{"name": "Content-Type", "value": content_type}, *(headers or [])],
        body=body,
        redirect_chain=redirects,
    )


def test_reordered_json_normalizes_to_an_exact_match() -> None:
    result = compare_responses(
        normalized('{"user":{"name":"Ada","id":7},"active":true}'),
        normalized('{"active":true,"user":{"id":7,"name":"Ada"}}'),
    )

    assert result["normalized_similarity"] == 1.0
    assert result["json"]["structural_similarity"] == 1.0
    assert result["json"]["changed_fields"] == []


def test_json_diff_explains_added_removed_and_changed_fields() -> None:
    result = compare_responses(
        normalized('{"id":17,"owner":"tenant-a","legacy":true}'),
        normalized('{"id":17,"owner":"tenant-b","role":"reader"}'),
    )

    assert result["json"]["added_fields"] == ["$.role"]
    assert result["json"]["removed_fields"] == ["$.legacy"]
    assert result["json"]["changed_fields"] == [
        {"path": "$.owner", "a": "tenant-a", "b": "tenant-b"}
    ]
    assert 0 < result["json"]["structural_similarity"] < 1


def test_dynamic_values_do_not_overwhelm_similarity_but_remain_explainable() -> None:
    first = '{"request_id":"87d95099-3f36-4df3-8c78-707755ea8490","at":"2026-10-03T10:00:00Z"}'
    second = '{"request_id":"b13e9ed4-f49d-4dc8-8c7a-ffdb77a0b65f","at":"2026-10-03T10:00:01Z"}'

    result = compare_responses(normalized(first), normalized(second))

    assert result["normalized_similarity"] == 1.0
    assert [item["path"] for item in result["json"]["changed_fields"]] == [
        "$.at",
        "$.request_id",
    ]


def test_text_status_type_redirect_and_header_differences_are_reported() -> None:
    result = compare_responses(
        normalized(
            "<p>allowed</p>",
            status=200,
            content_type="text/html; charset=utf-8",
            headers=[{"name": "ETag", "value": "first"}],
            redirects=["http://app.test/login"],
        ),
        normalized(
            "access denied",
            status=403,
            content_type="text/plain",
            headers=[{"name": "ETag", "value": "second"}],
        ),
    )

    assert result["status"] == {"a": 200, "b": 403, "changed": True}
    assert result["content_type"]["changed"] is True
    assert result["redirects"]["changed"] is True
    assert result["header_differences"] == [
        {"name": "content-type", "a": "text/html; charset=utf-8", "b": "text/plain"},
        {"name": "etag", "a": "first", "b": "second"},
    ]
    assert result["normalized_similarity"] < 0.5


def test_empty_non_json_bodies_compare_without_special_cases() -> None:
    result = compare_responses(
        normalized(None, status=204, content_type="text/plain"),
        normalized("", status=204, content_type="text/plain"),
    )

    assert result["body_size"] == {"a": 0, "b": 0, "delta": 0}
    assert result["normalized_similarity"] == 1.0
    assert result["json"]["present_a"] is False
