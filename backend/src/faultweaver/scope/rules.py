from dataclasses import dataclass
from posixpath import normpath
from urllib.parse import unquote, urlsplit


class InvalidUrlError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ScopeRuleValue:
    scheme: str
    hostname: str
    port: int
    path_prefix: str = "/"


def normalize_scheme(scheme: str) -> str:
    normalized = scheme.strip().lower()
    if normalized not in {"http", "https"}:
        raise ValueError("scheme must be http or https")
    return normalized


def normalize_hostname(hostname: str) -> str:
    normalized = hostname.strip().rstrip(".").lower()
    if not normalized or "/" in normalized or "@" in normalized:
        raise ValueError("hostname is invalid")
    try:
        return normalized.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ValueError("hostname is invalid") from error


def normalize_path(path: str) -> str:
    candidate = path or "/"
    for _ in range(3):
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded
    if unquote(candidate) != candidate:
        raise InvalidUrlError("path contains excessive nested encoding")
    if any(ord(character) < 32 or ord(character) == 127 for character in candidate):
        raise InvalidUrlError("path contains control characters")
    candidate = candidate.replace("\\", "/")
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    normalized = normpath(candidate)
    return "/" if normalized == "." else normalized


def normalize_path_prefix(path_prefix: str) -> str:
    try:
        return normalize_path(path_prefix)
    except InvalidUrlError as error:
        raise ValueError(str(error)) from error


def default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def split_http_url(url: str) -> tuple[str, str, int, str]:
    try:
        if any(ord(character) <= 32 or ord(character) == 127 for character in url):
            raise InvalidUrlError("URL contains whitespace or control characters")
        parsed = urlsplit(url)
        scheme = normalize_scheme(parsed.scheme)
        if parsed.username is not None or parsed.password is not None:
            raise InvalidUrlError("URL user information is not allowed")
        if parsed.hostname is None:
            raise InvalidUrlError("URL must include a hostname")
        hostname = normalize_hostname(parsed.hostname)
        port = parsed.port if parsed.port is not None else default_port(scheme)
        if not 1 <= port <= 65535:
            raise InvalidUrlError("URL port is invalid")
        path = normalize_path(parsed.path)
    except (ValueError, UnicodeError) as error:
        if isinstance(error, InvalidUrlError):
            raise
        raise InvalidUrlError("URL is invalid") from error
    return scheme, hostname, port, path


def is_url_in_scope(url: str, rules: list[ScopeRuleValue]) -> bool:
    try:
        scheme, hostname, port, path = split_http_url(url)
    except InvalidUrlError:
        return False

    for rule in rules:
        prefix = normalize_path_prefix(rule.path_prefix)
        path_matches = prefix == "/" or path == prefix or path.startswith(f"{prefix.rstrip('/')}/")
        if (
            scheme == rule.scheme
            and hostname == rule.hostname
            and port == rule.port
            and path_matches
        ):
            return True
    return False
