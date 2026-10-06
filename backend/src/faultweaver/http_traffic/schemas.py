from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from faultweaver.redaction import (
    exchange_secret_values,
    redact_body,
    redact_exchange_values,
    redact_headers,
    redact_query,
    redact_url,
)


class HeaderEntry(BaseModel):
    name: str
    value: str


class RawImportCreate(BaseModel):
    base_url: AnyHttpUrl
    raw: str = Field(min_length=1, max_length=2_000_000)


class ReplayCreate(BaseModel):
    identity_id: str | None = None
    method: str | None = Field(default=None, min_length=1, max_length=16)
    url: AnyHttpUrl | None = None
    headers: list[HeaderEntry] | None = None
    body: str | None = Field(default=None, max_length=2_000_000)

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class ExchangeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    engagement_id: str
    parent_exchange_id: str | None
    identity_id: str | None
    import_batch_id: str | None
    endpoint_id: str | None
    assessment_run_id: str | None
    discovered_from_exchange_id: str | None
    crawl_depth: int | None
    discovery_kind: str | None
    source_entry_index: int | None
    auth_source: str
    operator_modified: bool
    source: str
    method: str
    url: str
    host: str
    path: str
    query: str
    response_status: int | None
    response_elapsed_ms: float | None
    response_truncated: bool
    created_at: datetime


class ExchangeResponse(ExchangeSummary):
    crawl_error: str | None
    request_headers: list[HeaderEntry]
    request_body: str | None
    response_headers: list[HeaderEntry]
    response_body: str | None
    redirect_chain: list[str]


class ExchangeDetail(ExchangeResponse):
    raw_request: str


class ExchangeList(BaseModel):
    items: list[ExchangeSummary]
    total: int


def public_summary(exchange: object) -> ExchangeSummary:
    summary = ExchangeSummary.model_validate(exchange)
    return summary.model_copy(
        update={"url": redact_url(summary.url), "query": redact_query(summary.query)}
    )


def public_exchange(exchange: object) -> ExchangeResponse:
    legacy_identity = exchange.auth_source == "identity" and not all(  # type: ignore[attr-defined]
        "sensitive" in item
        for item in exchange.request_headers  # type: ignore[attr-defined]
    )
    public = ExchangeResponse(
        id=exchange.id,  # type: ignore[attr-defined]
        engagement_id=exchange.engagement_id,  # type: ignore[attr-defined]
        parent_exchange_id=exchange.parent_exchange_id,  # type: ignore[attr-defined]
        identity_id=exchange.identity_id,  # type: ignore[attr-defined]
        import_batch_id=exchange.import_batch_id,  # type: ignore[attr-defined]
        endpoint_id=exchange.endpoint_id,  # type: ignore[attr-defined]
        assessment_run_id=exchange.assessment_run_id,  # type: ignore[attr-defined]
        discovered_from_exchange_id=exchange.discovered_from_exchange_id,  # type: ignore[attr-defined]
        crawl_depth=exchange.crawl_depth,  # type: ignore[attr-defined]
        discovery_kind=exchange.discovery_kind,  # type: ignore[attr-defined]
        crawl_error=redact_body(exchange.crawl_error),  # type: ignore[attr-defined]
        source_entry_index=exchange.source_entry_index,  # type: ignore[attr-defined]
        auth_source=exchange.auth_source,  # type: ignore[attr-defined]
        operator_modified=exchange.operator_modified,  # type: ignore[attr-defined]
        source=exchange.source,  # type: ignore[attr-defined]
        method=exchange.method,  # type: ignore[attr-defined]
        url=redact_url(exchange.url),  # type: ignore[attr-defined]
        host=exchange.host,  # type: ignore[attr-defined]
        path=exchange.path,  # type: ignore[attr-defined]
        query=redact_query(exchange.query),  # type: ignore[attr-defined]
        request_headers=redact_headers(
            exchange.request_headers,  # type: ignore[attr-defined]
            # Older identity replays lack immutable header provenance. Fail
            # closed instead of trusting the identity's mutable current fields.
            redact_all=legacy_identity,
        ),
        request_body=redact_body(exchange.request_body),  # type: ignore[attr-defined]
        response_status=exchange.response_status,  # type: ignore[attr-defined]
        response_headers=redact_headers(exchange.response_headers),  # type: ignore[attr-defined]
        response_body=redact_body(exchange.response_body),  # type: ignore[attr-defined]
        response_elapsed_ms=exchange.response_elapsed_ms,  # type: ignore[attr-defined]
        response_truncated=exchange.response_truncated,  # type: ignore[attr-defined]
        redirect_chain=[redact_url(item) for item in exchange.redirect_chain],  # type: ignore[attr-defined]
        created_at=exchange.created_at,  # type: ignore[attr-defined]
    )
    return ExchangeResponse.model_validate(
        redact_exchange_values(
            public.model_dump(),
            exchange_secret_values(
                exchange.request_headers,
                legacy_identity=legacy_identity,  # type: ignore[attr-defined]
            ),
        )
    )
