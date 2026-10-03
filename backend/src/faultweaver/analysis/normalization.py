from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from faultweaver.redaction import redact_body, redact_headers

_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
_LONG_HEX = re.compile(r"\b[0-9a-f]{20,}\b", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"\b\d{10,}\b")
_WHITESPACE = re.compile(r"\s+")
SELECTED_HEADERS = (
    "cache-control",
    "content-language",
    "content-type",
    "etag",
    "location",
    "vary",
    "www-authenticate",
)


@dataclass(frozen=True, slots=True)
class NormalizedResponse:
    status: int | None
    content_type: str | None
    body_length: int
    normalized_text: str
    json_value: Any | None
    json_structure: list[str]
    json_fields: dict[str, Any]
    selected_headers: dict[str, str]
    redirect_chain: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_response(
    *,
    status: int | None,
    headers: list[dict[str, str]],
    body: str | None,
    redirect_chain: list[str] | None = None,
) -> NormalizedResponse:
    safe_headers = redact_headers(headers)
    header_map = _header_map(safe_headers)
    safe_body = redact_body(body) or ""
    content_type = header_map.get("content-type")
    if content_type is not None:
        content_type = content_type.split(";", 1)[0].strip().lower()

    json_value: Any | None = None
    json_structure: list[str] = []
    json_fields: dict[str, Any] = {}
    try:
        json_value = json.loads(safe_body) if safe_body else None
    except json.JSONDecodeError:
        pass
    else:
        if json_value is not None:
            json_structure = sorted(_structure(json_value))
            json_fields = _flatten(json_value)

    canonical = (
        json.dumps(json_value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if json_value is not None
        else safe_body
    )
    return NormalizedResponse(
        status=status,
        content_type=content_type,
        body_length=len((body or "").encode("utf-8")),
        normalized_text=_normalize_dynamic_text(canonical),
        json_value=json_value,
        json_structure=json_structure,
        json_fields=json_fields,
        selected_headers={key: header_map[key] for key in SELECTED_HEADERS if key in header_map},
        redirect_chain=list(redirect_chain or []),
    )


def _header_map(headers: list[dict[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for header in headers:
        key = header["name"].lower()
        result[key] = f"{result[key]}, {header['value']}" if key in result else header["value"]
    return result


def _normalize_dynamic_text(value: str) -> str:
    value = _UUID.sub("<uuid>", value)
    value = _TIMESTAMP.sub("<timestamp>", value)
    value = _LONG_HEX.sub("<opaque>", value)
    value = _LONG_NUMBER.sub("<number>", value)
    return _WHITESPACE.sub(" ", value).strip()


def _structure(value: Any, path: str = "$") -> set[str]:
    if isinstance(value, dict):
        items = {f"{path}:object"}
        for key, item in value.items():
            items.update(_structure(item, f"{path}.{key}"))
        return items
    if isinstance(value, list):
        items = {f"{path}:array"}
        for item in value:
            items.update(_structure(item, f"{path}[]"))
        return items
    return {f"{path}:{_json_type(value)}"}


def _flatten(value: Any, path: str = "$") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            result.update(_flatten(item, f"{path}.{key}"))
        return result
    if isinstance(value, list):
        result = {}
        for index, item in enumerate(value):
            result.update(_flatten(item, f"{path}[{index}]"))
        return result
    return {path: value}


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"
