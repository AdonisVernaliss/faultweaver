from __future__ import annotations

import base64
import binascii
import json
import math
from datetime import datetime
from typing import Any

from faultweaver.imports.canonical import (
    CanonicalHttpRecord,
    CanonicalizationError,
    ParseResult,
    ParserLimits,
)


class HarParseError(ValueError):
    """Raised when a HAR document is structurally invalid."""


def parse_har(content: str, limits: ParserLimits) -> ParseResult:
    _check_document_size(content, limits)
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise HarParseError("HAR is not valid JSON") from error
    if not isinstance(document, dict) or not isinstance(document.get("log"), dict):
        raise HarParseError("HAR document requires a log object")
    entries = document["log"].get("entries")
    if not isinstance(entries, list):
        raise HarParseError("HAR log requires an entries array")
    if len(entries) > limits.max_entries:
        raise HarParseError(f"HAR contains more than {limits.max_entries} entries")

    result = ParseResult(total_records=len(entries))
    for index, entry in enumerate(entries):
        try:
            record = _parse_entry(entry, index, limits)
        except (HarParseError, CanonicalizationError) as error:
            result.skipped_count += 1
            result.warnings.append(f"Entry {index}: {error}")
            continue
        result.records.append(record)
        result.warnings.extend(record.warnings)
    return result


def _parse_entry(entry: object, index: int, limits: ParserLimits) -> CanonicalHttpRecord:
    if not isinstance(entry, dict):
        raise HarParseError("entry must be an object")
    request = entry.get("request")
    if not isinstance(request, dict):
        raise HarParseError("request is missing")
    method = request.get("method")
    url = request.get("url")
    if not isinstance(method, str) or not isinstance(url, str):
        raise HarParseError("request method and URL are required")
    warnings: list[str] = []
    request_headers = _headers(request.get("headers"), index, "request", warnings)
    _append_request_cookies(request_headers, request.get("cookies"), index, warnings)
    request_body = None
    post_data = request.get("postData")
    if isinstance(post_data, dict) and isinstance(post_data.get("text"), str):
        request_body, truncated = _truncate_text(post_data["text"], limits.max_request_body_bytes)
        if truncated:
            warnings.append(f"Entry {index}: request body was truncated")

    response_status = None
    response_headers: list[dict[str, str]] = []
    response_body = None
    response_truncated = False
    redirect_chain: list[str] = []
    response = entry.get("response")
    if isinstance(response, dict):
        status = response.get("status")
        if isinstance(status, int) and 100 <= status <= 999:
            response_status = status
        elif status not in (None, 0):
            warnings.append(f"Entry {index}: response status was ignored")
        response_headers = _headers(response.get("headers"), index, "response", warnings)
        _append_response_cookies(response_headers, response.get("cookies"), index, warnings)
        response_body, response_truncated = _response_content(
            response.get("content"), index, limits.max_response_body_bytes, warnings
        )
        redirect_url = response.get("redirectURL")
        if isinstance(redirect_url, str) and redirect_url:
            redirect_chain.append(redirect_url)

    elapsed = entry.get("time")
    elapsed_ms = (
        float(elapsed)
        if isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed >= 0
        else None
    )
    observed_at = _timestamp(entry.get("startedDateTime"), index, warnings)
    record = CanonicalHttpRecord(
        method=method,
        url=url,
        request_headers=request_headers,
        request_body=request_body,
        response_status=response_status,
        response_headers=response_headers,
        response_body=response_body,
        response_elapsed_ms=elapsed_ms,
        response_truncated=response_truncated,
        redirect_chain=redirect_chain,
        source_entry_index=index,
        observed_at=observed_at,
        warnings=warnings,
    )
    record.validated_parts()
    return record


def _headers(value: object, index: int, label: str, warnings: list[str]) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"Entry {index}: malformed {label} headers were ignored")
        return []
    headers: list[dict[str, str]] = []
    for position, item in enumerate(value):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            warnings.append(f"Entry {index}: malformed {label} header {position} was ignored")
            continue
        raw_value = item.get("value", "")
        if not isinstance(raw_value, str):
            warnings.append(f"Entry {index}: malformed {label} header {position} was ignored")
            continue
        headers.append({"name": item["name"], "value": raw_value})
    return headers


def _append_request_cookies(
    headers: list[dict[str, str]], value: object, index: int, warnings: list[str]
) -> None:
    if any(item["name"].lower() == "cookie" for item in headers) or value is None:
        return
    cookie_values = _cookie_pairs(value, index, "request", warnings)
    if cookie_values:
        headers.append({"name": "Cookie", "value": "; ".join(cookie_values)})


def _append_response_cookies(
    headers: list[dict[str, str]], value: object, index: int, warnings: list[str]
) -> None:
    if any(item["name"].lower() == "set-cookie" for item in headers) or value is None:
        return
    for pair in _cookie_pairs(value, index, "response", warnings):
        headers.append({"name": "Set-Cookie", "value": pair})


def _cookie_pairs(value: object, index: int, label: str, warnings: list[str]) -> list[str]:
    if not isinstance(value, list):
        warnings.append(f"Entry {index}: malformed {label} cookies were ignored")
        return []
    pairs: list[str] = []
    for position, item in enumerate(value):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("value"), str)
        ):
            warnings.append(f"Entry {index}: malformed {label} cookie {position} was ignored")
            continue
        pairs.append(f"{item['name']}={item['value']}")
    return pairs


def _response_content(
    value: object, index: int, maximum: int, warnings: list[str]
) -> tuple[str | None, bool]:
    if not isinstance(value, dict) or not isinstance(value.get("text"), str):
        return None, False
    text = value["text"]
    if value.get("encoding") == "base64":
        try:
            raw = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            warnings.append(f"Entry {index}: invalid base64 response body was omitted")
            return None, False
        truncated = len(raw) > maximum
        raw = raw[:maximum]
        try:
            return raw.decode("utf-8"), truncated
        except UnicodeDecodeError:
            warnings.append(f"Entry {index}: binary response body was omitted")
            return f"[binary content omitted: {len(raw)} bytes]", truncated
    return _truncate_text(text, maximum)


def _truncate_text(value: str, maximum: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum:
        return value, False
    return encoded[:maximum].decode("utf-8", errors="ignore"), True


def _timestamp(value: Any, index: int, warnings: list[str]) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        warnings.append(f"Entry {index}: invalid timestamp was ignored")
        return None


def _check_document_size(content: str, limits: ParserLimits) -> None:
    if len(content.encode("utf-8")) > limits.max_document_bytes:
        raise HarParseError(f"HAR exceeds the {limits.max_document_bytes} byte limit")
