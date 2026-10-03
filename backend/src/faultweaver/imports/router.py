from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.imports.canonical import ParseResult
from faultweaver.imports.curl import CurlParseError, parse_curl
from faultweaver.imports.har import HarParseError, parse_har
from faultweaver.imports.models import AttackSurfaceEndpoint, ImportBatch
from faultweaver.imports.openapi import OpenApiParseError, parse_openapi
from faultweaver.imports.schemas import (
    AttackSurfaceEndpointResponse,
    ImportBatchResponse,
    ImportDocument,
    ImportEndpointPreview,
    ImportPreviewResponse,
    ImportRequestPreview,
    ImportResultResponse,
)
from faultweaver.imports.service import (
    observed_count,
    parser_limits,
    persist_observed_import,
    persist_openapi_import,
    public_batch,
)
from faultweaver.redaction import redact_url
from faultweaver.scope.models import ScopeRule
from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope

router = APIRouter(tags=["imports"])
SessionDep = Annotated[Session, Depends(get_session)]
ImportFormat = Literal["har", "curl", "openapi"]


@router.post(
    "/api/engagements/{engagement_id}/imports/{import_format}/preview",
    response_model=ImportPreviewResponse,
)
def preview_import(
    engagement_id: str,
    import_format: ImportFormat,
    payload: ImportDocument,
    request: Request,
    session: SessionDep,
) -> ImportPreviewResponse:
    get_engagement_or_404(session, engagement_id)
    parsed = _parse(import_format, payload.content, request)
    return _preview(import_format, parsed, _scope_values(session, engagement_id))


@router.post(
    "/api/engagements/{engagement_id}/imports/{import_format}",
    response_model=ImportResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_document(
    engagement_id: str,
    import_format: ImportFormat,
    payload: ImportDocument,
    request: Request,
    session: SessionDep,
) -> ImportResultResponse:
    get_engagement_or_404(session, engagement_id)
    parsed = _parse(import_format, payload.content, request)
    if import_format == "openapi":
        return persist_openapi_import(
            session,
            engagement_id=engagement_id,
            filename=payload.filename,
            content=payload.content,
            parsed=parsed,
        )
    return persist_observed_import(
        session,
        engagement_id=engagement_id,
        import_format=import_format,
        filename=payload.filename,
        content=payload.content,
        parsed=parsed,
        scopes=_scope_values(session, engagement_id),
    )


@router.get(
    "/api/engagements/{engagement_id}/imports",
    response_model=list[ImportBatchResponse],
)
def list_import_batches(engagement_id: str, session: SessionDep) -> list[ImportBatchResponse]:
    get_engagement_or_404(session, engagement_id)
    batches = session.scalars(
        select(ImportBatch)
        .where(ImportBatch.engagement_id == engagement_id)
        .order_by(ImportBatch.created_at.desc())
    )
    return [public_batch(batch) for batch in batches]


@router.get(
    "/api/engagements/{engagement_id}/attack-surface",
    response_model=list[AttackSurfaceEndpointResponse],
)
def list_attack_surface(
    engagement_id: str,
    session: SessionDep,
    q: str | None = None,
    source: str | None = None,
    endpoint_state: Annotated[str | None, Query(alias="state")] = None,
) -> list[AttackSurfaceEndpointResponse]:
    get_engagement_or_404(session, engagement_id)
    filters = [AttackSurfaceEndpoint.engagement_id == engagement_id]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                AttackSurfaceEndpoint.path_template.ilike(pattern),
                AttackSurfaceEndpoint.host.ilike(pattern),
                AttackSurfaceEndpoint.method.ilike(pattern),
            )
        )
    endpoints = list(
        session.scalars(
            select(AttackSurfaceEndpoint)
            .where(*filters)
            .order_by(
                AttackSurfaceEndpoint.host,
                AttackSurfaceEndpoint.path_template,
                AttackSurfaceEndpoint.method,
            )
        )
    )
    responses = [_public_endpoint(session, endpoint) for endpoint in endpoints]
    if source:
        responses = [item for item in responses if source in item.sources]
    if endpoint_state:
        responses = [item for item in responses if item.state == endpoint_state]
    return responses


def _parse(import_format: ImportFormat, content: str, request: Request) -> ParseResult:
    limits = parser_limits(request.app.state.settings)
    try:
        if import_format == "har":
            return parse_har(content, limits)
        if import_format == "curl":
            return parse_curl(content, limits)
        return parse_openapi(content, limits)
    except (HarParseError, CurlParseError, OpenApiParseError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


def _preview(
    import_format: ImportFormat, parsed: ParseResult, scopes: list[ScopeRuleValue]
) -> ImportPreviewResponse:
    requests: list[ImportRequestPreview] = []
    warnings = list(parsed.warnings)
    accepted_count = 0
    response_count = 0
    out_of_scope = 0
    for record in parsed.records:
        allowed = is_url_in_scope(record.url, scopes)
        if allowed:
            accepted_count += 1
        else:
            out_of_scope += 1
            warnings.append(
                f"Entry {record.source_entry_index}: request is outside the authorized scope"
            )
        if record.response_status is not None:
            response_count += 1
        content_type = next(
            (
                item["value"].split(";", 1)[0]
                for item in record.request_headers
                if item["name"].lower() == "content-type"
            ),
            None,
        )
        requests.append(
            ImportRequestPreview(
                source_entry_index=record.source_entry_index,
                method=record.method.upper(),
                url=redact_url(record.url),
                header_count=len(record.request_headers),
                cookie_count=sum(
                    1 for item in record.request_headers if item["name"].lower() == "cookie"
                ),
                body_kind=content_type,
                body_bytes=len((record.request_body or "").encode("utf-8")),
                response_status=record.response_status,
                scope_allowed=allowed,
            )
        )
    endpoints = [
        ImportEndpointPreview(
            method=endpoint.method,
            path_template=endpoint.path_template,
            server_url=endpoint.server_url,
            operation_id=_string_detail(endpoint.details, "operation_id"),
            auth=[
                str(item.get("kind"))
                for item in endpoint.details.get("security", [])
                if isinstance(item, dict) and item.get("kind")
            ],
        )
        for endpoint in parsed.endpoints
    ]
    return ImportPreviewResponse(
        import_format=import_format,
        total_records=parsed.total_records,
        accepted_count=accepted_count + len(parsed.endpoints),
        response_count=response_count,
        skipped_count=parsed.skipped_count + out_of_scope,
        warnings=warnings,
        requests=requests[:100],
        endpoints=endpoints[:200],
    )


def _public_endpoint(
    session: Session, endpoint: AttackSurfaceEndpoint
) -> AttackSurfaceEndpointResponse:
    count = observed_count(session, endpoint.id)
    state = (
        "observed_and_declared"
        if count and endpoint.declared_by_openapi
        else "observed_only"
        if count
        else "declared_only"
    )
    return AttackSurfaceEndpointResponse(
        id=endpoint.id,
        method=endpoint.method,
        scheme=endpoint.scheme,
        host=endpoint.host,
        port=endpoint.port,
        path_template=endpoint.path_template,
        sources=endpoint.sources,
        observed_request_count=count,
        declared_by_openapi=endpoint.declared_by_openapi,
        state=state,
        metadata=endpoint.details,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )


def _scope_values(session: Session, engagement_id: str) -> list[ScopeRuleValue]:
    rules = session.scalars(
        select(ScopeRule).where(
            ScopeRule.engagement_id == engagement_id,
            ScopeRule.active.is_(True),
        )
    )
    return [
        ScopeRuleValue(
            scheme=rule.scheme,
            hostname=rule.hostname,
            port=rule.port,
            path_prefix=rule.path_prefix,
        )
        for rule in rules
    ]


def _string_detail(details: dict[str, object], key: str) -> str | None:
    value = details.get(key)
    return value if isinstance(value, str) else None
