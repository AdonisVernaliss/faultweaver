from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit


class CanonicalizationError(ValueError):
    """Raised when parser output cannot form a canonical HTTP record."""


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_document_bytes: int
    max_entries: int
    max_request_body_bytes: int
    max_response_body_bytes: int


@dataclass(slots=True)
class CanonicalHttpRecord:
    method: str
    url: str
    request_headers: list[dict[str, str]] = field(default_factory=list)
    request_body: str | None = None
    response_status: int | None = None
    response_headers: list[dict[str, str]] = field(default_factory=list)
    response_body: str | None = None
    response_elapsed_ms: float | None = None
    response_truncated: bool = False
    redirect_chain: list[str] = field(default_factory=list)
    source_entry_index: int | None = None
    observed_at: datetime | None = None
    warnings: list[str] = field(default_factory=list)

    def validated_parts(self) -> tuple[str, str, str, str]:
        method = self.method.strip().upper()
        parsed = urlsplit(self.url)
        if not method or len(method) > 16:
            raise CanonicalizationError("HTTP method is invalid")
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise CanonicalizationError("HTTP URL must use http or https and include a host")
        try:
            port = parsed.port
        except ValueError as error:
            raise CanonicalizationError("HTTP URL contains an invalid port") from error
        del port
        return method, parsed.hostname.lower(), parsed.path or "/", parsed.query


@dataclass(slots=True)
class DeclaredEndpoint:
    method: str
    path_template: str
    server_url: str | None
    details: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParseResult:
    records: list[CanonicalHttpRecord] = field(default_factory=list)
    endpoints: list[DeclaredEndpoint] = field(default_factory=list)
    total_records: int = 0
    skipped_count: int = 0
    warnings: list[str] = field(default_factory=list)
