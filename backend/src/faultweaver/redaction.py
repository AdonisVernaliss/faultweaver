from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, quote, unquote_plus, urlencode, urlsplit, urlunsplit

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
_PASSWORD_COMPONENT = re.compile(r"(^|[_-])pass(word|phrase)?(s)?([_-]|$)", re.IGNORECASE)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_FORM_FIELD = re.compile(r"(?P<prefix>(?:^|[&\s])(?P<name>[^=&\s]+)=)[^&\s]*")
_HEADER_SECRET = re.compile(
    r"(?im)^(authorization|cookie|proxy-authorization|set-cookie|x-api-key)\s*:\s*.*$"
)
_INLINE_HEADER_SECRET = re.compile(
    r"(?i)(\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:\s*)"
    r"(?:bearer\s+)?[^\s,;]+"
)
_INLINE_NAMED_SECRET = re.compile(r"(?i)(\b(?:api[_-]?key|password|secret|token)\s*:\s*)[^\s,;]+")


def is_sensitive_header(name: str) -> bool:
    lowered = name.strip().lower()
    return lowered in _SENSITIVE_HEADERS or "api-key" in lowered or "apikey" in lowered


def is_sensitive_key(name: str) -> bool:
    normalized = _CAMEL_CASE_BOUNDARY.sub("_", name)
    return bool(_SENSITIVE_KEY.search(normalized) or _PASSWORD_COMPONENT.search(normalized))


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
        safe = _redact_form_fields(body)
        safe = _HEADER_SECRET.sub(r"\1: [REDACTED]", safe)
        safe = _INLINE_HEADER_SECRET.sub(r"\1[REDACTED]", safe)
        return _INLINE_NAMED_SECRET.sub(r"\1[REDACTED]", safe)
    return json.dumps(_redact_value(value), separators=(",", ":"), ensure_ascii=False)


def _redact_form_fields(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if is_sensitive_key(unquote_plus(match.group("name"))):
            return f"{match.group('prefix')}{REDACTED}"
        return match.group(0)

    return _FORM_FIELD.sub(replace, value)


def redact_query(query: str) -> str:
    return urlencode(
        [
            (name, REDACTED if is_sensitive_key(name) else value)
            for name, value in parse_qsl(query, keep_blank_values=True)
        ],
        doseq=True,
    )


def redact_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        netloc = parsed.netloc
        if parsed.username is not None:
            hostname = parsed.hostname or ""
            if ":" in hostname:
                hostname = f"[{hostname}]"
            port = f":{parsed.port}" if parsed.port is not None else ""
            netloc = f"{quote(REDACTED, safe='')}@{hostname}{port}"
    except ValueError:
        return REDACTED
    fragment = redact_query(parsed.fragment) if "=" in parsed.fragment else parsed.fragment
    return urlunsplit(
        parsed._replace(netloc=netloc, query=redact_query(parsed.query), fragment=fragment)
    )


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return _redact_value(dict(value))


def _redact_value(value: Any, key: str | None = None) -> Any:
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        if (
            isinstance(value.get("name"), str)
            and "value" in value
            and is_sensitive_header(value["name"])
        ):
            return {**value, "value": REDACTED}
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
    redacting_filter = SecretRedactingFilter()
    if not any(isinstance(item, SecretRedactingFilter) for item in root.filters):
        root.addFilter(redacting_filter)
    handlers = [*root.handlers]
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            handlers.extend(logger.handlers)
    for handler in handlers:
        if not any(isinstance(item, SecretRedactingFilter) for item in handler.filters):
            handler.addFilter(redacting_filter)
