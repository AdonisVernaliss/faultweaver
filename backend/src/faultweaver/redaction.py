from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}
_SENSITIVE_KEY = re.compile(
    r"(^|[_-])(api[_-]?key|authorization|cookie|pass(word|phrase)?|secret|token)(s)?$",
    re.IGNORECASE,
)
_FORM_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|password|secret|token)=)[^&\s]*"
)


def is_sensitive_header(name: str) -> bool:
    lowered = name.strip().lower()
    return lowered in _SENSITIVE_HEADERS or "api-key" in lowered or "apikey" in lowered


def is_sensitive_key(name: str) -> bool:
    return bool(_SENSITIVE_KEY.search(name))


def redact_headers(headers: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "name": header["name"],
            "value": REDACTED if is_sensitive_header(header["name"]) else header["value"],
        }
        for header in headers
    ]


def redact_body(body: str | None) -> str | None:
    if body is None:
        return None
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return _FORM_SECRET.sub(r"\1[REDACTED]", body)
    return json.dumps(_redact_value(value), separators=(",", ":"), ensure_ascii=False)


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return _redact_value(dict(value))


def _redact_value(value: Any, key: str | None = None) -> Any:
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {item_key: _redact_value(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def sanitize_for_log(value: object) -> object:
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [sanitize_for_log(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_log(item) for item in value)
    if isinstance(value, str):
        return redact_body(value)
    return value


class SecretRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_for_log(record.msg)
        record.args = sanitize_for_log(record.args)
        return True


def install_log_redaction() -> None:
    root = logging.getLogger()
    if any(isinstance(item, SecretRedactingFilter) for item in root.filters):
        return
    root.addFilter(SecretRedactingFilter())
