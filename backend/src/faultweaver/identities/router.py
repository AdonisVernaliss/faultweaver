from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.identities.models import Identity
from faultweaver.identities.schemas import IdentityCreate, IdentityResponse, IdentityUpdate
from faultweaver.redaction import REDACTED, is_sensitive_header

router = APIRouter(tags=["identities"])
SessionDep = Annotated[Session, Depends(get_session)]


def public_identity(identity: Identity) -> IdentityResponse:
    return IdentityResponse(
        id=identity.id,
        engagement_id=identity.engagement_id,
        name=identity.name,
        description=identity.description,
        is_anonymous=identity.is_anonymous,
        bearer_token=REDACTED if identity.bearer_token is not None else None,
        api_key_header=identity.api_key_header,
        api_key_value=REDACTED if identity.api_key_value is not None else None,
        cookies=[{"name": item["name"], "value": REDACTED} for item in identity.cookies],
        custom_headers=[
            {
                "name": item["name"],
                "value": REDACTED if is_sensitive_header(item["name"]) else item["value"],
            }
            for item in identity.custom_headers
        ],
        created_at=identity.created_at,
        updated_at=identity.updated_at,
    )


def get_identity_or_404(session: Session, engagement_id: str, identity_id: str) -> Identity:
    identity = session.scalar(
        select(Identity).where(
            Identity.id == identity_id,
            Identity.engagement_id == engagement_id,
            Identity.archived_at.is_(None),
        )
    )
    if identity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")
    return identity


@router.post(
    "/api/engagements/{engagement_id}/identities",
    response_model=IdentityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_identity(
    engagement_id: str, payload: IdentityCreate, session: SessionDep
) -> IdentityResponse:
    get_engagement_or_404(session, engagement_id)
    identity = Identity(
        engagement_id=engagement_id,
        name=payload.name.strip(),
        description=payload.description,
        bearer_token=payload.bearer_token,
        api_key_header=payload.api_key_header,
        api_key_value=payload.api_key_value,
        cookies=[item.model_dump() for item in payload.cookies],
        custom_headers=[item.model_dump() for item in payload.custom_headers],
    )
    session.add(identity)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Identity name already exists in this engagement",
        ) from error
    session.refresh(identity)
    return public_identity(identity)


@router.get("/api/engagements/{engagement_id}/identities", response_model=list[IdentityResponse])
def list_identities(engagement_id: str, session: SessionDep) -> list[IdentityResponse]:
    get_engagement_or_404(session, engagement_id)
    identities = session.scalars(
        select(Identity)
        .where(Identity.engagement_id == engagement_id, Identity.archived_at.is_(None))
        .order_by(Identity.is_anonymous.desc(), Identity.name)
    )
    return [public_identity(identity) for identity in identities]


@router.get(
    "/api/engagements/{engagement_id}/identities/{identity_id}",
    response_model=IdentityResponse,
)
def get_identity(engagement_id: str, identity_id: str, session: SessionDep) -> IdentityResponse:
    identity = get_identity_or_404(session, engagement_id, identity_id)
    return public_identity(identity)


@router.patch(
    "/api/engagements/{engagement_id}/identities/{identity_id}",
    response_model=IdentityResponse,
)
def update_identity(
    engagement_id: str, identity_id: str, payload: IdentityUpdate, session: SessionDep
) -> IdentityResponse:
    identity = get_identity_or_404(session, engagement_id, identity_id)
    if identity.is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Anonymous identity is immutable"
        )
    updates = payload.model_dump(exclude_unset=True)
    for field in ("cookies", "custom_headers"):
        if field in updates and updates[field] is not None:
            updates[field] = [item.model_dump() for item in getattr(payload, field)]
    for key, value in updates.items():
        setattr(identity, key, value.strip() if key == "name" and value else value)
    if (identity.api_key_header is None) != (identity.api_key_value is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="api_key_header and api_key_value must be provided together",
        )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Identity name exists"
        ) from error
    session.refresh(identity)
    return public_identity(identity)


@router.delete(
    "/api/engagements/{engagement_id}/identities/{identity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_identity(engagement_id: str, identity_id: str, session: SessionDep) -> None:
    identity = get_identity_or_404(session, engagement_id, identity_id)
    if identity.is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Anonymous identity cannot be deleted"
        )
    identity.archived_at = datetime.now(UTC)
    session.commit()
