from __future__ import annotations

import re
from posixpath import normpath
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from faultweaver.scope.rules import normalize_hostname, split_http_url

_PERCENT_ESCAPE = re.compile(r"%([0-9a-fA-F]{2})")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


class InvalidCrawlUrl(ValueError):
    pass


def canonicalize_url(url: str) -> str:
    """Return a conservative identity key without changing query ordering."""
    try:
        split_http_url(url)
        parsed = urlsplit(url.strip())
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise InvalidCrawlUrl("Only HTTP and HTTPS URLs can be assessed")
        if parsed.username is not None or parsed.password is not None:
            raise InvalidCrawlUrl("URL user information is not allowed")
        if parsed.hostname is None:
            raise InvalidCrawlUrl("URL must include a hostname")
        hostname = normalize_hostname(parsed.hostname)
        port = parsed.port
    except (UnicodeError, ValueError) as error:
        if isinstance(error, InvalidCrawlUrl):
            raise
        raise InvalidCrawlUrl("URL is invalid") from error

    if any(ord(character) < 32 for character in unquote(parsed.path)):
        raise InvalidCrawlUrl("URL path contains control characters")
    if ":" in hostname:
        hostname = f"[{hostname}]"
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    raw_path = _normalize_percent(parsed.path or "/")
    trailing_slash = raw_path.endswith("/")
    path = normpath(raw_path.replace("\\", "/"))
    if not path.startswith("/"):
        path = f"/{path}"
    if trailing_slash and path != "/":
        path += "/"
    path = quote(unquote(path), safe="/%:@!$&'()*+,;=-._~")
    query = _normalize_percent(parsed.query)
    return urlunsplit((scheme, netloc, path, query, ""))


def resolve_url(base_url: str, reference: str) -> str:
    return canonicalize_url(urljoin(base_url, reference.strip()))


def _normalize_percent(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        return character if character in _UNRESERVED else f"%{match.group(1).upper()}"

    return _PERCENT_ESCAPE.sub(replace, value)
