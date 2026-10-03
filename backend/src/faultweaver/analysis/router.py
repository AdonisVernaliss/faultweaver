from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from faultweaver.analysis.candidates import authorization_candidate
from faultweaver.analysis.diffing import compare_responses
from faultweaver.analysis.models import Candidate, ResponseComparison
from faultweaver.analysis.normalization import normalize_response
from faultweaver.analysis.schemas import (
    AuthorizationMatrixCell,
    AuthorizationMatrixIdentity,
    AuthorizationMatrixResponse,
    AuthorizationMatrixRow,
    CandidateResponse,
    CandidateUpdate,
    ComparisonCreate,
    ComparisonResponse,
)
from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.http_traffic.replay import RedirectLimitError, ScopeViolationError
from faultweaver.http_traffic.router import _scope_values
from faultweaver.http_traffic.schemas import ReplayCreate, public_exchange
from faultweaver.http_traffic.service import build_replay_exchange
from faultweaver.identities.models import Identity

router = APIRouter(tags=["analysis"])
SessionDep = Annotated[Session, Depends(get_session)]


def public_candidate(candidate: Candidate) -> CandidateResponse:
    return CandidateResponse(
        id=candidate.id,
        engagement_id=candidate.engagement_id,
        comparison_id=candidate.comparison_id,
        original_exchange_id=candidate.original_exchange_id,
        supporting_replay_ids=[item.id for item in candidate.supporting_replays],
        title=candidate.title,
        category=candidate.category,
        confidence=candidate.confidence,
        status=candidate.status,
        reasoning=candidate.reasoning,
        notes=candidate.notes,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def public_comparison(
    session: Session, comparison: ResponseComparison
) -> ComparisonResponse:
    replay_a = session.get(HttpExchange, comparison.replay_a_id)
    replay_b = session.get(HttpExchange, comparison.replay_b_id)
    if replay_a is None or replay_b is None:
        raise RuntimeError("Comparison replay evidence is missing")
    candidate = session.scalar(
        select(Candidate).where(Candidate.comparison_id == comparison.id)
    )
    return ComparisonResponse(
        id=comparison.id,
        engagement_id=comparison.engagement_id,
        original_exchange_id=comparison.original_exchange_id,
        replay_a=public_exchange(replay_a),
        replay_b=public_exchange(replay_b),
        identity_a_id=comparison.identity_a_id,
        identity_b_id=comparison.identity_b_id,
        result=comparison.result,
        candidate=public_candidate(candidate) if candidate is not None else None,
        created_at=comparison.created_at,
    )


@router.post(
    "/api/requests/{request_id}/compare",
    response_model=ComparisonResponse,
    status_code=status.HTTP_201_CREATED,
)
def compare_identities(
    request_id: str,
    payload: ComparisonCreate,
    request: Request,
    session: SessionDep,
) -> ComparisonResponse:
    original = session.get(HttpExchange, request_id)
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    identity_ids = {payload.identity_a_id, payload.identity_b_id}
    identities = set(
        session.scalars(
            select(Identity.id).where(
                Identity.engagement_id == original.engagement_id,
                Identity.id.in_(identity_ids),
            )
        )
    )
    if identities != identity_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")

    try:
        replay_a = _replay_for_identity(
            session, original, payload.identity_a_id, request
        )
        replay_b = _replay_for_identity(
            session, original, payload.identity_b_id, request
        )
    except ScopeViolationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except (httpx.HTTPError, RedirectLimitError, ValidationError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    session.add_all([replay_a, replay_b])
    session.flush()
    normalized_a = _normalize_exchange(replay_a)
    normalized_b = _normalize_exchange(replay_b)
    comparison = ResponseComparison(
        engagement_id=original.engagement_id,
        original_exchange_id=original.id,
        replay_a_id=replay_a.id,
        replay_b_id=replay_b.id,
        identity_a_id=payload.identity_a_id,
        identity_b_id=payload.identity_b_id,
        result={
            "normalized_a": normalized_a.to_dict(),
            "normalized_b": normalized_b.to_dict(),
            "diff": compare_responses(normalized_a, normalized_b),
        },
    )
    session.add(comparison)
    session.flush()
    candidate = authorization_candidate(
        original=original,
        comparison=comparison,
        replay_a=replay_a,
        replay_b=replay_b,
    )
    if candidate is not None:
        session.add(candidate)
    session.commit()
    session.refresh(comparison)
    return public_comparison(session, comparison)


@router.get("/api/comparisons/{comparison_id}", response_model=ComparisonResponse)
def get_comparison(comparison_id: str, session: SessionDep) -> ComparisonResponse:
    comparison = session.get(ResponseComparison, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")
    return public_comparison(session, comparison)


@router.get(
    "/api/engagements/{engagement_id}/candidates",
    response_model=list[CandidateResponse],
)
def list_candidates(engagement_id: str, session: SessionDep) -> list[CandidateResponse]:
    get_engagement_or_404(session, engagement_id)
    candidates = session.scalars(
        select(Candidate)
        .where(Candidate.engagement_id == engagement_id)
        .order_by(Candidate.created_at.desc())
    )
    return [public_candidate(candidate) for candidate in candidates]


@router.get(
    "/api/engagements/{engagement_id}/candidates/{candidate_id}",
    response_model=CandidateResponse,
)
def get_candidate(
    engagement_id: str, candidate_id: str, session: SessionDep
) -> CandidateResponse:
    candidate = _candidate_or_404(session, engagement_id, candidate_id)
    return public_candidate(candidate)


@router.patch(
    "/api/engagements/{engagement_id}/candidates/{candidate_id}",
    response_model=CandidateResponse,
)
def update_candidate(
    engagement_id: str,
    candidate_id: str,
    payload: CandidateUpdate,
    session: SessionDep,
) -> CandidateResponse:
    candidate = _candidate_or_404(session, engagement_id, candidate_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(candidate, field, value)
    session.commit()
    session.refresh(candidate)
    return public_candidate(candidate)


@router.get(
    "/api/engagements/{engagement_id}/authorization-matrix",
    response_model=AuthorizationMatrixResponse,
)
def authorization_matrix(
    engagement_id: str, session: SessionDep
) -> AuthorizationMatrixResponse:
    get_engagement_or_404(session, engagement_id)
    identities = list(
        session.scalars(
            select(Identity)
            .where(Identity.engagement_id == engagement_id)
            .order_by(Identity.is_anonymous.desc(), Identity.name)
        )
    )
    originals = list(
        session.scalars(
            select(HttpExchange)
            .where(
                HttpExchange.engagement_id == engagement_id,
                HttpExchange.parent_exchange_id.is_(None),
            )
            .order_by(HttpExchange.created_at)
        )
    )
    rows: list[AuthorizationMatrixRow] = []
    for original in originals:
        replays = list(
            session.scalars(
                select(HttpExchange)
                .where(HttpExchange.parent_exchange_id == original.id)
                .order_by(HttpExchange.created_at.desc())
            )
        )
        latest_by_identity: dict[str, HttpExchange] = {}
        for replay in replays:
            if replay.identity_id is not None:
                latest_by_identity.setdefault(replay.identity_id, replay)
        cells: dict[str, AuthorizationMatrixCell] = {}
        for identity in identities:
            replay = latest_by_identity.get(identity.id)
            if replay is None:
                cells[identity.id] = AuthorizationMatrixCell(state="not_tested")
            elif replay.response_status is None:
                cells[identity.id] = AuthorizationMatrixCell(
                    state="missing_response", evidence_request_id=replay.id
                )
            else:
                cells[identity.id] = AuthorizationMatrixCell(
                    state="observed",
                    status=replay.response_status,
                    evidence_request_id=replay.id,
                )
        rows.append(
            AuthorizationMatrixRow(
                method=original.method,
                host=original.host,
                path=original.path,
                original_request_id=original.id,
                cells=cells,
            )
        )
    return AuthorizationMatrixResponse(
        identities=[
            AuthorizationMatrixIdentity(
                id=identity.id,
                name=identity.name,
                is_anonymous=identity.is_anonymous,
            )
            for identity in identities
        ],
        rows=rows,
    )


def _replay_for_identity(
    session: Session,
    original: HttpExchange,
    identity_id: str,
    request: Request,
) -> HttpExchange:
    return build_replay_exchange(
        session,
        original=original,
        payload=ReplayCreate(identity_id=identity_id),
        settings=request.app.state.settings,
        transport=request.app.state.http_transport,
        scopes=_scope_values(session, original.engagement_id),
    )


def _normalize_exchange(exchange: HttpExchange):
    return normalize_response(
        status=exchange.response_status,
        headers=exchange.response_headers,
        body=exchange.response_body,
        redirect_chain=exchange.redirect_chain,
    )


def _candidate_or_404(
    session: Session, engagement_id: str, candidate_id: str
) -> Candidate:
    candidate = session.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.engagement_id == engagement_id,
        )
    )
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate
