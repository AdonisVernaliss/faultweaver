from dataclasses import dataclass
from time import monotonic
from urllib.parse import urljoin

import httpx

from faultweaver.http_traffic.schemas import HeaderEntry
from faultweaver.identities.models import Identity
from faultweaver.redaction import is_sensitive_header
from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope, split_http_url

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class ScopeViolationError(ValueError):
    pass


class RedirectLimitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReplayResult:
    method: str
    url: str
    request_headers: list[dict[str, str]]
    request_body: str | None
    status: int
    response_headers: list[dict[str, str]]
    response_body: str
    elapsed_ms: float
    response_truncated: bool
    redirect_chain: list[str]


def apply_identity(
    headers: list[HeaderEntry],
    identity: Identity,
    *,
    managed_header_names: set[str],
) -> list[HeaderEntry]:
    """Replace known authentication material without changing unrelated headers."""
    retained = [
        header
        for header in headers
        if not is_sensitive_header(header.name) and header.name.lower() not in managed_header_names
    ]
    if identity.is_anonymous:
        return retained
    if identity.bearer_token is not None:
        retained.append(HeaderEntry(name="Authorization", value=f"Bearer {identity.bearer_token}"))
    if identity.api_key_header is not None and identity.api_key_value is not None:
        retained.append(HeaderEntry(name=identity.api_key_header, value=identity.api_key_value))
    if identity.cookies:
        cookie_value = "; ".join(
            f"{cookie['name']}={cookie['value']}" for cookie in identity.cookies
        )
        retained.append(HeaderEntry(name="Cookie", value=cookie_value))
    retained.extend(HeaderEntry.model_validate(item) for item in identity.custom_headers)
    return retained


def execute_replay(
    client: httpx.Client,
    *,
    method: str,
    url: str,
    headers: list[HeaderEntry],
    body: str | None,
    scopes: list[ScopeRuleValue],
    max_redirects: int,
    max_response_bytes: int,
    managed_header_names: frozenset[str] | set[str] = frozenset(),
) -> ReplayResult:
    current_method = method
    current_url = url
    current_headers = _safe_headers(headers)
    current_body = body
    redirects: list[str] = []
    started = monotonic()

    for redirect_number in range(max_redirects + 1):
        if not is_url_in_scope(current_url, scopes):
            raise ScopeViolationError("URL is outside the authorized scope")

        with client.stream(
            current_method,
            current_url,
            headers=current_headers,
            content=current_body,
            follow_redirects=False,
        ) as response:
            location = response.headers.get("location")
            response_headers = [
                {"name": key, "value": value} for key, value in response.headers.multi_items()
            ]
            if response.status_code not in REDIRECT_STATUSES or location is None:
                content, truncated = _read_limited(response, max_response_bytes)
                return ReplayResult(
                    method=current_method,
                    url=current_url,
                    request_headers=[
                        {"name": key, "value": value}
                        for key, value in response.request.headers.multi_items()
                    ],
                    request_body=current_body,
                    status=response.status_code,
                    response_headers=response_headers,
                    response_body=content.decode(response.encoding or "utf-8", errors="replace"),
                    elapsed_ms=round((monotonic() - started) * 1000, 3),
                    response_truncated=truncated,
                    redirect_chain=redirects,
                )
            response_status = response.status_code

        if redirect_number >= max_redirects:
            raise RedirectLimitError("Maximum redirect count exceeded")
        destination = urljoin(current_url, location)
        if not is_url_in_scope(destination, scopes):
            raise ScopeViolationError("Redirect is outside the authorized scope")
        redirects.append(destination)

        if _origin(current_url) != _origin(destination):
            current_headers = [
                (name, value)
                for name, value in current_headers
                if not is_sensitive_header(name) and name.lower() not in managed_header_names
            ]
            # Cookies have no port boundary. Do not let the client's jar undo
            # the explicit credential removal on a different authorized origin.
            client.cookies.clear()
        if response_status == 303 or (response_status in {301, 302} and current_method == "POST"):
            current_method = "GET"
            current_body = None
        current_url = destination

    raise RedirectLimitError("Maximum redirect count exceeded")


def _safe_headers(headers: list[HeaderEntry]) -> list[tuple[str, str]]:
    return [
        (header.name, header.value)
        for header in headers
        if header.name.lower() not in HOP_BY_HOP_HEADERS
    ]


def _origin(url: str) -> tuple[str, str, int]:
    scheme, hostname, port, _ = split_http_url(url)
    return scheme, hostname, port


def _read_limited(response: httpx.Response, limit: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    truncated = False
    for chunk in response.iter_bytes():
        remaining = limit - size
        if remaining <= 0:
            truncated = True
            break
        chunks.append(chunk[:remaining])
        size += min(len(chunk), remaining)
        if len(chunk) > remaining:
            truncated = True
            break
    return b"".join(chunks), truncated
