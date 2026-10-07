from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, load_only

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
)
from faultweaver.http_traffic.schemas import (
    ExchangeDetail,
    ExchangeList,
    ExchangeResponse,
    ExchangeSummary,
    RawImportCreate,
    ReplayCreate,
    public_exchange,
    public_summary,
)
from faultweaver.http_traffic.service import build_replay_exchange
from faultweaver.imports.service import attach_exchange_endpoint
from faultweaver.scope.models import ScopeRule
from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope

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
    session.flush()
    attach_exchange_endpoint(session, exchange, source="raw_import")
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
    source: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExchangeList:
    get_engagement_or_404(session, engagement_id)
    filters = [HttpExchange.engagement_id == engagement_id]
    if q and (needle := q.strip()):
        filters.append(
            or_(
                HttpExchange.url.icontains(needle, autoescape=True),
                HttpExchange.method.icontains(needle, autoescape=True),
                cast(HttpExchange.response_status, String).icontains(needle, autoescape=True),
            )
        )
    if method:
        filters.append(HttpExchange.method == method.upper())
    if response_status is not None:
        filters.append(HttpExchange.response_status == response_status)
    if source:
        filters.append(HttpExchange.source == source)

    total = session.scalar(select(func.count()).select_from(HttpExchange).where(*filters)) or 0
    items = list(
        session.scalars(
            select(HttpExchange)
            .options(
                load_only(
                    *(getattr(HttpExchange, name) for name in ExchangeSummary.model_fields),
                    raiseload=True,
                )
            )
            .where(*filters)
            .order_by(HttpExchange.created_at.desc(), HttpExchange.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return ExchangeList(items=[public_summary(item) for item in items], total=total)


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

    try:
        replay = build_replay_exchange(
            session,
            original=original,
            payload=payload,
            settings=request.app.state.settings,
            transport=request.app.state.http_transport,
            scopes=_scope_values(session, original.engagement_id),
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ScopeViolationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except (httpx.HTTPError, RedirectLimitError, ValidationError, UnicodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Replay failed; check the request and target",
        ) from error

    session.add(replay)
    session.commit()
    session.refresh(replay)
    return public_exchange(replay)
