from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from faultweaver.analysis.models import Candidate
from faultweaver.assessments.models import (
    AssessmentRun,
    BaselineObservation,
    CrawlDiscovery,
    CrawlForm,
)
from faultweaver.assessments.schemas import (
    AssessmentCreate,
    AssessmentDetail,
    AssessmentSummary,
    DiscoveryResponse,
    FormResponse,
    ObservationResponse,
)
from faultweaver.assessments.urls import canonicalize_url
from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.findings.service import allocate_display_id
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.redaction import redact_url
from faultweaver.scope.models import ScopeRule
from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope

router = APIRouter(tags=["baseline assessments"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "/api/engagements/{engagement_id}/assessments",
    response_model=AssessmentSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment(
    engagement_id: str,
    payload: AssessmentCreate,
    request: Request,
    session: SessionDep,
) -> AssessmentSummary:
    get_engagement_or_404(session, engagement_id)
    target = canonicalize_url(str(payload.target_url))
    scopes = _scope_values(session, engagement_id)
    if not is_url_in_scope(target, scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assessment target is outside the authorized scope",
        )
    display_id, number = allocate_display_id(session, engagement_id, "assessment")
    run = AssessmentRun(
        engagement_id=engagement_id,
        display_id=display_id,
        sequence_number=number,
        target_url=target,
        status="Pending",
        max_pages=payload.max_pages,
        max_depth=payload.max_depth,
        max_requests=payload.max_requests,
        requests_per_second=payload.requests_per_second,
        concurrency=payload.concurrency,
        request_timeout_seconds=payload.request_timeout_seconds,
        max_response_bytes=payload.max_response_bytes,
        max_query_variants_per_path=payload.max_query_variants_per_path,
        inspect_site_metadata=payload.inspect_site_metadata,
        warnings=[],
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    request.app.state.assessment_manager.start(run.id)
    return _summary(run)


@router.get(
    "/api/engagements/{engagement_id}/assessments",
    response_model=list[AssessmentSummary],
)
def list_assessments(engagement_id: str, session: SessionDep) -> list[AssessmentSummary]:
    get_engagement_or_404(session, engagement_id)
    runs = session.scalars(
        select(AssessmentRun)
        .where(AssessmentRun.engagement_id == engagement_id)
        .order_by(AssessmentRun.created_at.desc())
    )
    return [_summary(run) for run in runs]


@router.get(
    "/api/engagements/{engagement_id}/assessments/{run_id}",
    response_model=AssessmentDetail,
)
def get_assessment(engagement_id: str, run_id: str, session: SessionDep) -> AssessmentDetail:
    run = _run_or_404(session, engagement_id, run_id)
    discoveries = list(
        session.scalars(
            select(CrawlDiscovery)
            .where(CrawlDiscovery.assessment_run_id == run.id)
            .order_by(CrawlDiscovery.created_at)
        )
    )
    forms = list(
        session.scalars(
            select(CrawlForm)
            .where(CrawlForm.assessment_run_id == run.id)
            .order_by(CrawlForm.created_at)
        )
    )
    observations = list(
        session.scalars(
            select(BaselineObservation)
            .where(BaselineObservation.assessment_run_id == run.id)
            .order_by(BaselineObservation.classification, BaselineObservation.created_at)
        )
    )
    request_ids = list(
        session.scalars(
            select(HttpExchange.id)
            .where(HttpExchange.assessment_run_id == run.id)
            .order_by(HttpExchange.created_at)
        )
    )
    candidate_ids = list(
        session.scalars(
            select(Candidate.id)
            .where(Candidate.assessment_run_id == run.id)
            .order_by(Candidate.created_at)
        )
    )
    return AssessmentDetail(
        **_summary(run).model_dump(),
        discoveries=[_discovery(item) for item in discoveries],
        forms=[FormResponse.model_validate(item) for item in forms],
        observations=[ObservationResponse.model_validate(item) for item in observations],
        request_ids=request_ids,
        candidate_ids=candidate_ids,
    )


@router.post(
    "/api/engagements/{engagement_id}/assessments/{run_id}/stop",
    response_model=AssessmentSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def stop_assessment(
    engagement_id: str,
    run_id: str,
    request: Request,
    session: SessionDep,
) -> AssessmentSummary:
    run = _run_or_404(session, engagement_id, run_id)
    if run.status not in {"Pending", "Running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Assessment is already {run.status.lower()}",
        )
    run.stop_requested = True
    session.commit()
    request.app.state.assessment_manager.stop(run.id)
    session.refresh(run)
    return _summary(run)


def _summary(run: AssessmentRun) -> AssessmentSummary:
    value = AssessmentSummary.model_validate(run)
    value.target_url = redact_url(value.target_url)
    value.current_url = redact_url(value.current_url) if value.current_url else None
    return value


def _discovery(item: CrawlDiscovery) -> DiscoveryResponse:
    value = DiscoveryResponse.model_validate(item)
    value.url = redact_url(value.url)
    value.canonical_url = redact_url(value.canonical_url)
    return value


def _run_or_404(session: Session, engagement_id: str, run_id: str) -> AssessmentRun:
    run = session.scalar(
        select(AssessmentRun).where(
            AssessmentRun.id == run_id,
            AssessmentRun.engagement_id == engagement_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return run


def _scope_values(session: Session, engagement_id: str) -> list[ScopeRuleValue]:
    return [
        ScopeRuleValue(
            scheme=rule.scheme,
            hostname=rule.hostname,
            port=rule.port,
            path_prefix=rule.path_prefix,
        )
        for rule in session.scalars(
            select(ScopeRule).where(
                ScopeRule.engagement_id == engagement_id,
                ScopeRule.active.is_(True),
            )
        )
    ]
