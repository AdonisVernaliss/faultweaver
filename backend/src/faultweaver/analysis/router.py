from datetime import UTC, datetime
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
    CandidateReview,
    CandidateUpdate,
    ComparisonCreate,
    ComparisonResponse,
)
from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.findings.models import Evidence, Finding, OperatorNote
from faultweaver.findings.router import public_finding
from faultweaver.findings.schemas import FindingPromotion, FindingResponse
from faultweaver.findings.service import add_history, allocate_display_id
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.http_traffic.replay import RedirectLimitError, ScopeViolationError
from faultweaver.http_traffic.router import _scope_values
from faultweaver.http_traffic.schemas import ReplayCreate, public_exchange
from faultweaver.http_traffic.service import build_replay_exchange
from faultweaver.identities.models import Identity
from faultweaver.redaction import redact_body

router = APIRouter(tags=["analysis"])
SessionDep = Annotated[Session, Depends(get_session)]


def public_candidate(session: Session, candidate: Candidate) -> CandidateResponse:
    comparison = (
        session.get(ResponseComparison, candidate.comparison_id)
        if candidate.comparison_id is not None
        else None
    )
    original = session.get(HttpExchange, candidate.original_exchange_id)
    finding = session.scalar(select(Finding).where(Finding.candidate_id == candidate.id))
    identities: list[dict[str, str]] = []
    comparison_result: dict[str, object] = {}
    if comparison is not None:
        comparison_result = comparison.result
        identity_rows = session.scalars(
            select(Identity).where(
                Identity.id.in_([comparison.identity_a_id, comparison.identity_b_id])
            )
        )
        identities = [{"id": item.id, "name": item.name} for item in identity_rows]
    replays = list(candidate.supporting_replays)
    operator_notes = session.scalars(
        select(OperatorNote)
        .where(OperatorNote.candidate_id == candidate.id)
        .order_by(OperatorNote.created_at)
    )
    return CandidateResponse(
        id=candidate.id,
        engagement_id=candidate.engagement_id,
        comparison_id=candidate.comparison_id,
        original_exchange_id=candidate.original_exchange_id,
        assessment_run_id=candidate.assessment_run_id,
        endpoint_id=candidate.endpoint_id,
        check_id=candidate.check_id,
        suggested_severity=candidate.suggested_severity,
        affected_exchange_ids=candidate.affected_exchange_ids,
        supporting_replay_ids=[item.id for item in candidate.supporting_replays],
        title=candidate.title,
        category=candidate.category,
        confidence=candidate.confidence,
        status=candidate.status,
        review_decision=candidate.review_decision,
        reviewed_at=candidate.reviewed_at,
        archived_at=candidate.archived_at,
        finding_id=finding.id if finding else None,
        reasoning=candidate.reasoning,
        notes=redact_body(candidate.notes) or "",
        target={
            "method": original.method if original else "",
            "host": original.host if original else "",
            "path": original.path if original else "",
        },
        original=public_exchange(original) if original else None,
        supporting_replays=[public_exchange(item) for item in replays],
        comparison_result=comparison_result,
        identities=identities,
        response_statuses=[
            {
                "exchange_id": item.id,
                "identity_id": item.identity_id,
                "status": item.response_status,
            }
            for item in replays
        ],
        operator_notes=[
            {
                "id": item.id,
                "author_label": item.author_label,
                "body": item.body,
                "created_at": item.created_at,
            }
            for item in operator_notes
        ],
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def public_comparison(session: Session, comparison: ResponseComparison) -> ComparisonResponse:
    replay_a = session.get(HttpExchange, comparison.replay_a_id)
    replay_b = session.get(HttpExchange, comparison.replay_b_id)
    if replay_a is None or replay_b is None:
        raise RuntimeError("Comparison replay evidence is missing")
    candidate = session.scalar(select(Candidate).where(Candidate.comparison_id == comparison.id))
    return ComparisonResponse(
        id=comparison.id,
        engagement_id=comparison.engagement_id,
        original_exchange_id=comparison.original_exchange_id,
        replay_a=public_exchange(replay_a),
        replay_b=public_exchange(replay_b),
        identity_a_id=comparison.identity_a_id,
        identity_b_id=comparison.identity_b_id,
        result=comparison.result,
        candidate=public_candidate(session, candidate) if candidate is not None else None,
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
                Identity.archived_at.is_(None),
            )
        )
    )
    if identities != identity_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")

    try:
        replay_a = _replay_for_identity(session, original, payload.identity_a_id, request)
        replay_b = _replay_for_identity(session, original, payload.identity_b_id, request)
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
        .where(Candidate.engagement_id == engagement_id, Candidate.archived_at.is_(None))
        .order_by(Candidate.created_at.desc())
    )
    return [public_candidate(session, candidate) for candidate in candidates]


@router.get(
    "/api/engagements/{engagement_id}/candidates/{candidate_id}",
    response_model=CandidateResponse,
)
def get_candidate(engagement_id: str, candidate_id: str, session: SessionDep) -> CandidateResponse:
    candidate = _candidate_or_404(session, engagement_id, candidate_id)
    return public_candidate(session, candidate)


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
    updates = payload.model_dump(exclude_unset=True)
    if "notes" in updates:
        updates["notes"] = redact_body(updates["notes"]) or ""
    for field, value in updates.items():
        setattr(candidate, field, value)
    session.commit()
    session.refresh(candidate)
    return public_candidate(session, candidate)


@router.post(
    "/api/engagements/{engagement_id}/candidates/{candidate_id}/review",
    response_model=CandidateResponse,
)
def review_candidate(
    engagement_id: str,
    candidate_id: str,
    payload: CandidateReview,
    session: SessionDep,
) -> CandidateResponse:
    candidate = _candidate_or_404(session, engagement_id, candidate_id)
    if session.scalar(select(Finding).where(Finding.candidate_id == candidate.id)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Promoted candidates cannot be reclassified",
        )
    candidate.review_decision = payload.decision
    candidate.reviewed_at = datetime.now(UTC)
    candidate.status = "reviewed"
    if payload.note.strip():
        session.add(
            OperatorNote(
                engagement_id=engagement_id,
                candidate_id=candidate.id,
                author_label="Operator",
                body=redact_body(payload.note) or "",
            )
        )
    session.commit()
    session.refresh(candidate)
    return public_candidate(session, candidate)


@router.post(
    "/api/engagements/{engagement_id}/candidates/{candidate_id}/promote",
    response_model=FindingResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote_candidate(
    engagement_id: str,
    candidate_id: str,
    payload: FindingPromotion,
    session: SessionDep,
) -> FindingResponse:
    candidate = _candidate_or_404(session, engagement_id, candidate_id)
    existing = session.scalar(select(Finding).where(Finding.candidate_id == candidate.id))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Candidate already promoted to {existing.display_id}",
        )
    original = session.get(HttpExchange, candidate.original_exchange_id)
    display_id, number = allocate_display_id(session, engagement_id, "finding")
    finding = Finding(
        engagement_id=engagement_id,
        candidate_id=candidate.id,
        display_id=display_id,
        sequence_number=number,
        title=redact_body(payload.title or candidate.title) or candidate.title,
        category=payload.category or candidate.category,
        severity=payload.severity,
        status="Open",
        affected_asset=redact_body(payload.affected_asset or (original.host if original else ""))
        or "",
        affected_endpoints=[redact_body(item) or "" for item in payload.affected_endpoints]
        or ([original.path] if original else []),
        description=redact_body(payload.description) or "",
        impact=redact_body(payload.impact) or "",
        reproduction_steps=[redact_body(item) or "" for item in payload.reproduction_steps],
        remediation=redact_body(payload.remediation) or "",
        references=[redact_body(item) or "" for item in payload.references],
        supporting_original_exchange_id=candidate.original_exchange_id,
        supporting_comparison_id=candidate.comparison_id,
    )
    session.add(finding)
    session.flush()
    evidence_source = Evidence.source_candidate_id == candidate.id
    if candidate.comparison_id is not None:
        evidence_source = evidence_source | (
            Evidence.source_comparison_id == candidate.comparison_id
        )
    for evidence in session.scalars(
        select(Evidence).where(
            Evidence.engagement_id == engagement_id,
            Evidence.finding_id.is_(None),
            evidence_source,
        )
    ):
        evidence.finding_id = finding.id
    candidate.review_decision = "Confirmed"
    candidate.reviewed_at = datetime.now(UTC)
    candidate.status = "promoted"
    add_history(
        session,
        finding.id,
        "candidate_promoted",
        f"Candidate promoted to {display_id}",
        {"candidate_id": candidate.id, "finding_id": display_id},
    )
    session.commit()
    session.refresh(finding)
    return public_finding(session, finding)


@router.delete(
    "/api/engagements/{engagement_id}/candidates/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_candidate(engagement_id: str, candidate_id: str, session: SessionDep) -> None:
    candidate = _candidate_or_404(session, engagement_id, candidate_id)
    finding = session.scalar(select(Finding).where(Finding.candidate_id == candidate.id))
    if finding is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Candidate is retained by {finding.display_id}",
        )
    candidate.archived_at = datetime.now(UTC)
    session.commit()


@router.get(
    "/api/engagements/{engagement_id}/authorization-matrix",
    response_model=AuthorizationMatrixResponse,
)
def authorization_matrix(engagement_id: str, session: SessionDep) -> AuthorizationMatrixResponse:
    get_engagement_or_404(session, engagement_id)
    identities = list(
        session.scalars(
            select(Identity)
            .where(Identity.engagement_id == engagement_id, Identity.archived_at.is_(None))
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


def _candidate_or_404(session: Session, engagement_id: str, candidate_id: str) -> Candidate:
    candidate = session.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.engagement_id == engagement_id,
            Candidate.archived_at.is_(None),
        )
    )
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate
