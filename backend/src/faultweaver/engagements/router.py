from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from faultweaver.database import get_session
from faultweaver.engagements.models import Engagement
from faultweaver.engagements.schemas import (
    EngagementCreate,
    EngagementDetail,
    EngagementResponse,
)
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.identities.models import Identity
from faultweaver.scope.models import ScopeRule

router = APIRouter(prefix="/api/engagements", tags=["engagements"])
SessionDep = Annotated[Session, Depends(get_session)]


def get_engagement_or_404(session: Session, engagement_id: str) -> Engagement:
    engagement = session.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")
    return engagement


@router.post("", response_model=EngagementResponse, status_code=status.HTTP_201_CREATED)
def create_engagement(payload: EngagementCreate, session: SessionDep) -> Engagement:
    engagement = Engagement(name=payload.name, description=payload.description)
    session.add(engagement)
    session.flush()
    session.add(
        Identity(
            engagement_id=engagement.id,
            name="Anonymous",
            description="No authentication material",
            is_anonymous=True,
        )
    )
    session.commit()
    session.refresh(engagement)
    return engagement


@router.get("", response_model=list[EngagementResponse])
def list_engagements(session: SessionDep) -> list[Engagement]:
    return list(session.scalars(select(Engagement).order_by(Engagement.updated_at.desc())))


@router.get("/{engagement_id}", response_model=EngagementDetail)
def get_engagement(engagement_id: str, session: SessionDep) -> dict[str, object]:
    engagement = get_engagement_or_404(session, engagement_id)
    scope_count = session.scalar(
        select(func.count()).select_from(ScopeRule).where(ScopeRule.engagement_id == engagement_id)
    )
    request_count = session.scalar(
        select(func.count())
        .select_from(HttpExchange)
        .where(HttpExchange.engagement_id == engagement_id)
    )
    return {
        **EngagementResponse.model_validate(engagement).model_dump(),
        "scope_count": scope_count or 0,
        "request_count": request_count or 0,
    }
