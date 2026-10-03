from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.scope.models import ScopeRule
from faultweaver.scope.schemas import ScopeCreate, ScopeResponse

router = APIRouter(prefix="/api/engagements/{engagement_id}/scopes", tags=["scope"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=ScopeResponse, status_code=status.HTTP_201_CREATED)
def create_scope(
    engagement_id: str,
    payload: ScopeCreate,
    session: SessionDep,
) -> ScopeRule:
    get_engagement_or_404(session, engagement_id)
    rule = ScopeRule(
        engagement_id=engagement_id,
        scheme=payload.scheme,
        hostname=payload.hostname,
        port=payload.resolved_port(),
        path_prefix=payload.path_prefix,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.get("", response_model=list[ScopeResponse])
def list_scopes(engagement_id: str, session: SessionDep) -> list[ScopeRule]:
    get_engagement_or_404(session, engagement_id)
    return list(
        session.scalars(
            select(ScopeRule)
            .where(ScopeRule.engagement_id == engagement_id)
            .order_by(ScopeRule.hostname, ScopeRule.path_prefix)
        )
    )
