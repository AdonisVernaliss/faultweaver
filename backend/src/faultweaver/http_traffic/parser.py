import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from faultweaver.scope.rules import InvalidUrlError, split_http_url

REQUEST_LINE = re.compile(
    r"^(?P<method>[A-Za-z][A-Za-z0-9!#$%&'*+.^_`|~-]{0,31}) "
    r"(?P<target>\S+) HTTP/(?P<version>1\.[01]|2)$"
)


class HttpParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedRequest:
    method: str
    url: str
    host: str
    path: str
    query: str
    headers: list[dict[str, str]]
    body: str | None


def parse_raw_request(raw: str, base_url: str) -> ParsedRequest:
    normalized = raw.replace("\r\n", "\n")
    head, separator, body = normalized.partition("\n\n")
    lines = head.splitlines()
    if not lines:
        raise HttpParseError("Request is empty")
    request_line = REQUEST_LINE.fullmatch(lines[0].strip())
    if request_line is None:
        raise HttpParseError("Request line is invalid")

    headers: list[dict[str, str]] = []
    for line in lines[1:]:
        if line.startswith((" ", "\t")):
            raise HttpParseError("Folded headers are not supported")
        name, colon, value = line.partition(":")
        if not colon or not name.strip():
            raise HttpParseError("Header line is invalid")
        headers.append({"name": name.strip(), "value": value.strip()})

    target = request_line.group("target")
    try:
        base = urlsplit(base_url)
        split_http_url(base_url)
        if target.startswith(("http://", "https://")):
            url = target
        elif target.startswith("/"):
            host = _first_header(headers, "host") or base.netloc
            url = urlunsplit((base.scheme, host, *urlsplit(target)[2:]))
        else:
            raise HttpParseError("Only origin-form and absolute-form targets are supported")
        _, host, _, path = split_http_url(url)
    except (InvalidUrlError, ValueError) as error:
        if isinstance(error, HttpParseError):
            raise
        raise HttpParseError("Request URL is invalid") from error

    query = urlsplit(url).query
    return ParsedRequest(
        method=request_line.group("method").upper(),
        url=url,
        host=host,
        path=path,
        query=query,
        headers=headers,
        body=body if separator and body else None,
    )


def render_raw_request(exchange: object) -> str:
    return render_raw_request_parts(
        method=exchange.method,  # type: ignore[attr-defined]
        path=exchange.path,  # type: ignore[attr-defined]
        query=exchange.query,  # type: ignore[attr-defined]
        headers=exchange.request_headers,  # type: ignore[attr-defined]
        body=exchange.request_body,  # type: ignore[attr-defined]
    )


def render_raw_request_parts(
    *,
    method: str,
    path: str,
    query: str,
    headers: list[dict[str, str]],
    body: str | None,
) -> str:
    target = f"{path}?{query}" if query else path
    lines = [f"{method} {target} HTTP/1.1"]
    lines.extend(f"{header['name']}: {header['value']}" for header in headers)
    lines.append("")
    lines.append(body or "")
    return "\r\n".join(lines)


def _first_header(headers: list[dict[str, str]], name: str) -> str | None:
    lowered = name.lower()
    return next((header["value"] for header in headers if header["name"].lower() == lowered), None)
