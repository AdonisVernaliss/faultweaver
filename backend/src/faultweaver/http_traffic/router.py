from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.http_traffic.parser import (
    HttpParseError,
    parse_raw_request,
    render_raw_request_parts,
)
from faultweaver.http_traffic.replay import (
    RedirectLimitError,
    ScopeViolationError,
    apply_identity,
    execute_replay,
)
from faultweaver.http_traffic.schemas import (
    ExchangeDetail,
    ExchangeList,
    ExchangeResponse,
    HeaderEntry,
    RawImportCreate,
    ReplayCreate,
    public_exchange,
)
from faultweaver.identities.models import Identity
from faultweaver.scope.models import ScopeRule
from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope, split_http_url

router = APIRouter(tags=["http traffic"])
SessionDep = Annotated[Session, Depends(get_session)]


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


@router.post(
    "/api/engagements/{engagement_id}/traffic/raw",
    response_model=ExchangeResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_raw_request(
    engagement_id: str,
    payload: RawImportCreate,
    session: SessionDep,
) -> ExchangeResponse:
    get_engagement_or_404(session, engagement_id)
    try:
        parsed = parse_raw_request(payload.raw, str(payload.base_url))
    except HttpParseError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    if not is_url_in_scope(parsed.url, _scope_values(session, engagement_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Imported request is outside the authorized scope",
        )

    exchange = HttpExchange(
        engagement_id=engagement_id,
        source="raw_import",
        method=parsed.method,
        url=parsed.url,
        host=parsed.host,
        path=parsed.path,
        query=parsed.query,
        request_headers=parsed.headers,
        request_body=parsed.body,
    )
    session.add(exchange)
    session.commit()
    session.refresh(exchange)
    return public_exchange(exchange)


@router.get("/api/engagements/{engagement_id}/requests", response_model=ExchangeList)
def list_requests(
    engagement_id: str,
    session: SessionDep,
    q: str | None = None,
    method: str | None = None,
    response_status: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExchangeList:
    get_engagement_or_404(session, engagement_id)
    filters = [HttpExchange.engagement_id == engagement_id]
    if q:
        pattern = f"%{q}%"
        filters.append(or_(HttpExchange.url.ilike(pattern), HttpExchange.path.ilike(pattern)))
    if method:
        filters.append(HttpExchange.method == method.upper())
    if response_status is not None:
        filters.append(HttpExchange.response_status == response_status)

    total = session.scalar(select(func.count()).select_from(HttpExchange).where(*filters)) or 0
    items = list(
        session.scalars(
            select(HttpExchange)
            .where(*filters)
            .order_by(HttpExchange.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return ExchangeList(
        items=[public_exchange(item) for item in items], total=total
    )


@router.get("/api/requests/{request_id}", response_model=ExchangeDetail)
def get_request(request_id: str, session: SessionDep) -> dict[str, object]:
    exchange = session.get(HttpExchange, request_id)
    if exchange is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    public = public_exchange(exchange)
    return {
        **public.model_dump(),
        "raw_request": render_raw_request_parts(
            method=public.method,
            path=public.path,
            query=public.query,
            headers=[header.model_dump() for header in public.request_headers],
            body=public.request_body,
        ),
    }


@router.post(
    "/api/requests/{request_id}/replay",
    response_model=ExchangeResponse,
    status_code=status.HTTP_201_CREATED,
)
def replay_request(
    request_id: str,
    payload: ReplayCreate,
    request: Request,
    session: SessionDep,
) -> ExchangeResponse:
    original = session.get(HttpExchange, request_id)
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    method = payload.method or original.method
    url = str(payload.url) if payload.url is not None else original.url
    headers = payload.headers if payload.headers is not None else [
        HeaderEntry.model_validate(item) for item in original.request_headers
    ]
    body = payload.body if "body" in payload.model_fields_set else original.request_body
    identity: Identity | None = None
    auth_source = "original"
    if payload.identity_id is not None:
        identity = session.scalar(
            select(Identity).where(
                Identity.id == payload.identity_id,
                Identity.engagement_id == original.engagement_id,
            )
        )
        if identity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found"
            )
        engagement_identities = session.scalars(
            select(Identity).where(Identity.engagement_id == original.engagement_id)
        )
        managed_header_names = {
            name.lower()
            for item in engagement_identities
            for name in (
                *[header["name"] for header in item.custom_headers],
                *([item.api_key_header] if item.api_key_header else []),
            )
        }
        headers = apply_identity(
            headers, identity, managed_header_names=managed_header_names
        )
        auth_source = "identity"
    settings = request.app.state.settings

    try:
        with httpx.Client(
            transport=request.app.state.http_transport,
            timeout=settings.request_timeout_seconds,
        ) as client:
            result = execute_replay(
                client,
                method=method,
                url=url,
                headers=headers,
                body=body,
                scopes=_scope_values(session, original.engagement_id),
                max_redirects=settings.max_redirects,
                max_response_bytes=settings.max_response_bytes,
            )
        _, host, _, path = split_http_url(result.url)
    except ScopeViolationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except (httpx.HTTPError, RedirectLimitError, ValidationError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    replay = HttpExchange(
        engagement_id=original.engagement_id,
        parent_exchange_id=original.id,
        identity_id=identity.id if identity is not None else None,
        auth_source=auth_source,
        operator_modified=bool(
            {"method", "url", "headers", "body"}.intersection(payload.model_fields_set)
        ),
        source="replay",
        method=result.method,
        url=result.url,
        host=host,
        path=path,
        query=urlsplit(result.url).query,
        request_headers=result.request_headers,
        request_body=result.request_body,
        response_status=result.status,
        response_headers=result.response_headers,
        response_body=result.response_body,
        response_elapsed_ms=result.elapsed_ms,
        response_truncated=result.response_truncated,
        redirect_chain=result.redirect_chain,
    )
    session.add(replay)
    session.commit()
    session.refresh(replay)
    return public_exchange(replay)
