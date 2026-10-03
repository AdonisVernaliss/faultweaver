from __future__ import annotations

import re
import shlex
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from faultweaver.imports.canonical import (
    CanonicalHttpRecord,
    CanonicalizationError,
    ParseResult,
    ParserLimits,
)


class CurlParseError(ValueError):
    """Raised when a cURL command cannot be represented safely."""


_SHELL_EXPANSION = re.compile(r"\$\(|`|\$\{")
_UNSUPPORTED_WITH_VALUE = {
    "-o": "output",
    "--output": "output",
    "-T": "upload-file",
    "--upload-file": "upload-file",
    "-K": "config",
    "--config": "config",
    "--proxy": "proxy",
    "--resolve": "resolve",
    "--connect-to": "connect-to",
    "--unix-socket": "unix-socket",
}
_UNSUPPORTED_FLAGS = {"-O", "--remote-name"}
_IGNORED_FLAGS = {"--compressed", "--insecure", "-k", "--silent", "-s", "--location", "-L"}


def parse_curl(content: str, limits: ParserLimits) -> ParseResult:
    if len(content.encode("utf-8")) > limits.max_document_bytes:
        raise CurlParseError(f"cURL command exceeds the {limits.max_document_bytes} byte limit")
    if _SHELL_EXPANSION.search(content):
        raise CurlParseError("Shell expansion and command substitution are not supported")
    normalized = re.sub(r"\\\r?\n", " ", content).strip()
    try:
        tokens = shlex.split(normalized, posix=True)
    except ValueError as error:
        raise CurlParseError("cURL command contains malformed quoting") from error
    if not tokens or tokens[0].lower() not in {"curl", "curl.exe"}:
        raise CurlParseError("Input must begin with curl")

    method: str | None = None
    headers: list[dict[str, str]] = []
    bodies: list[str] = []
    urls: list[str] = []
    get_mode = False
    warnings: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"-X", "--request"}:
            method, index = _required_value(tokens, index, token)
        elif token.startswith("--request="):
            method = token.split("=", 1)[1]
        elif token in {"-H", "--header"}:
            value, index = _required_value(tokens, index, token)
            headers.append(_parse_header(value))
        elif token.startswith("--header="):
            headers.append(_parse_header(token.split("=", 1)[1]))
        elif token in {"-b", "--cookie"}:
            value, index = _required_value(tokens, index, token)
            if value.startswith("@"):
                raise CurlParseError("Cookie files are not supported")
            headers.append({"name": "Cookie", "value": value})
        elif token.startswith("--cookie="):
            value = token.split("=", 1)[1]
            if value.startswith("@"):
                raise CurlParseError("Cookie files are not supported")
            headers.append({"name": "Cookie", "value": value})
        elif token in {"-d", "--data", "--data-raw", "--data-binary", "--json"}:
            value, index = _required_value(tokens, index, token)
            _append_body(bodies, value, token)
            if token == "--json":
                _ensure_header(headers, "Content-Type", "application/json")
                _ensure_header(headers, "Accept", "application/json")
        elif any(
            token.startswith(prefix)
            for prefix in ("--data=", "--data-raw=", "--data-binary=", "--json=")
        ):
            option, value = token.split("=", 1)
            _append_body(bodies, value, option)
            if option == "--json":
                _ensure_header(headers, "Content-Type", "application/json")
                _ensure_header(headers, "Accept", "application/json")
        elif token == "-G" or token == "--get":
            get_mode = True
        elif token == "--url":
            value, index = _required_value(tokens, index, token)
            urls.append(value)
        elif token.startswith("--url="):
            urls.append(token.split("=", 1)[1])
        elif token in _UNSUPPORTED_WITH_VALUE:
            _, index = _required_value(tokens, index, token)
            warnings.append(f"Option {token} ({_UNSUPPORTED_WITH_VALUE[token]}) was ignored")
        elif token in _UNSUPPORTED_FLAGS:
            warnings.append(f"Option {token} is not supported and was ignored")
        elif (
            token.startswith("--proxy=")
            or token.startswith("--resolve=")
            or token.startswith("--connect-to=")
        ):
            warnings.append(f"Option {token.split('=', 1)[0]} was ignored")
        elif token in _IGNORED_FLAGS:
            warnings.append(f"Transport option {token} was ignored")
        elif token.startswith("-"):
            raise CurlParseError(f"Unsupported cURL option: {token}")
        else:
            urls.append(token)
        index += 1

    if len(urls) != 1:
        raise CurlParseError("Exactly one request URL is required")
    url = urls[0]
    body = "&".join(bodies) if bodies else None
    if body is not None and len(body.encode("utf-8")) > limits.max_request_body_bytes:
        raise CurlParseError(
            f"cURL request body exceeds the {limits.max_request_body_bytes} byte limit"
        )
    if get_mode and body:
        url = _append_query(url, body)
        body = None
    resolved_method = (method or ("POST" if body is not None else "GET")).upper()
    record = CanonicalHttpRecord(
        method=resolved_method,
        url=url,
        request_headers=headers,
        request_body=body,
        source_entry_index=0,
        warnings=warnings,
    )
    try:
        record.validated_parts()
    except CanonicalizationError as error:
        raise CurlParseError(str(error)) from error
    return ParseResult(records=[record], total_records=1, warnings=warnings)


def _required_value(tokens: list[str], index: int, option: str) -> tuple[str, int]:
    if index + 1 >= len(tokens):
        raise CurlParseError(f"Option {option} requires a value")
    return tokens[index + 1], index + 1


def _parse_header(value: str) -> dict[str, str]:
    if ":" not in value:
        raise CurlParseError("Headers must use the 'Name: value' form")
    name, header_value = value.split(":", 1)
    if not name.strip():
        raise CurlParseError("Header name cannot be empty")
    return {"name": name.strip(), "value": header_value.lstrip()}


def _append_body(bodies: list[str], value: str, option: str) -> None:
    if value.startswith("@"):
        raise CurlParseError(f"File-backed {option} values are not supported")
    bodies.append(value)


def _ensure_header(headers: list[dict[str, str]], name: str, value: str) -> None:
    if not any(item["name"].lower() == name.lower() for item in headers):
        headers.append({"name": name, "value": value})


def _append_query(url: str, body: str) -> str:
    parsed = urlsplit(url)
    existing = parse_qsl(parsed.query, keep_blank_values=True)
    incoming = parse_qsl(body, keep_blank_values=True)
    return urlunsplit(parsed._replace(query=urlencode([*existing, *incoming])))
