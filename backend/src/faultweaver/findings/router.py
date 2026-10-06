from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, load_only

from faultweaver.analysis.models import Candidate, ResponseComparison
from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.findings.models import (
    Evidence,
    Finding,
    FindingLifecycleEvent,
    OperatorNote,
    Retest,
    retest_evidence,
)
from faultweaver.findings.schemas import (
    EvidenceCreate,
    EvidenceResponse,
    EvidenceSummary,
    FindingResponse,
    FindingUpdate,
    HistoryResponse,
    LatestRetestResponse,
    NoteCreate,
    NoteResponse,
    RelatedAttackChainResponse,
    RetestCreate,
    RetestResponse,
    RetestUpdate,
)
from faultweaver.findings.service import add_history, allocate_display_id
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.http_traffic.schemas import public_exchange
from faultweaver.identities.models import Identity
from faultweaver.redaction import redact_body, redact_mapping

router = APIRouter(tags=["findings"])
SessionDep = Annotated[Session, Depends(get_session)]


def _notes(session: Session, target: str, target_id: str) -> list[NoteResponse]:
    column = getattr(OperatorNote, f"{target}_id")
    notes = session.scalars(
        select(OperatorNote).where(column == target_id).order_by(OperatorNote.created_at)
    )
    return [
        NoteResponse(id=n.id, author_label=n.author_label, body=n.body, created_at=n.created_at)
        for n in notes
    ]


def public_evidence(session: Session, item: Evidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=item.id,
        engagement_id=item.engagement_id,
        display_id=item.display_id,
        evidence_type=item.evidence_type,
        title=item.title,
        snapshot=redact_mapping(item.snapshot),
        source_exchange_id=item.source_exchange_id,
        source_comparison_id=item.source_comparison_id,
        source_candidate_id=item.source_candidate_id,
        finding_id=item.finding_id,
        author_label=item.author_label,
        captured_at=item.captured_at,
        notes=_notes(session, "evidence", item.id),
    )


def public_retest(session: Session, item: Retest) -> RetestResponse:
    finding = session.get(Finding, item.finding_id)
    evidence_ids = list(
        session.scalars(
            select(retest_evidence.c.evidence_id).where(retest_evidence.c.retest_id == item.id)
        )
    )
    return RetestResponse(
        id=item.id,
        engagement_id=item.engagement_id,
        finding_id=item.finding_id,
        finding_display_id=finding.display_id if finding else "",
        display_id=item.display_id,
        status=item.status,
        tested_at=item.tested_at,
        operator_notes=item.operator_notes,
        evidence_ids=evidence_ids,
        created_at=item.created_at,
        updated_at=item.updated_at,
        notes=_notes(session, "retest", item.id),
    )


def public_finding(session: Session, finding: Finding, *, detail: bool = True) -> FindingResponse:
    from faultweaver.attack_chains.models import AttackChain, AttackChainStep

    retests = list(
        session.scalars(
            select(Retest)
            .where(Retest.finding_id == finding.id)
            .order_by(Retest.tested_at.desc(), Retest.created_at.desc())
        )
    )
    latest = retests[0] if retests else None
    evidence_ids = list(
        session.scalars(
            select(Evidence.id)
            .where(Evidence.finding_id == finding.id)
            .order_by(Evidence.sequence_number)
        )
    )
    events = list(
        session.scalars(
            select(FindingLifecycleEvent)
            .where(FindingLifecycleEvent.finding_id == finding.id)
            .order_by(FindingLifecycleEvent.created_at)
        )
    )
    attack_chains = list(
        session.scalars(
            select(AttackChain)
            .join(AttackChainStep, AttackChainStep.attack_chain_id == AttackChain.id)
            .where(AttackChainStep.finding_id == finding.id)
            .order_by(AttackChain.sequence_number)
        ).unique()
    )
    return FindingResponse(
        id=finding.id,
        engagement_id=finding.engagement_id,
        display_id=finding.display_id,
        candidate_id=finding.candidate_id,
        title=finding.title,
        category=finding.category,
        severity=finding.severity,
        status=finding.status,
        affected_asset=finding.affected_asset,
        affected_endpoints=finding.affected_endpoints,
        description=finding.description,
        impact=finding.impact,
        reproduction_steps=finding.reproduction_steps,
        remediation=finding.remediation,
        references=finding.references,
        supporting_original_exchange_id=finding.supporting_original_exchange_id,
        supporting_comparison_id=finding.supporting_comparison_id,
        confirmed_at=finding.confirmed_at,
        created_at=finding.created_at,
        updated_at=finding.updated_at,
        archived_at=finding.archived_at,
        latest_retest=(
            LatestRetestResponse(
                display_id=latest.display_id, status=latest.status, tested_at=latest.tested_at
            )
            if latest
            else None
        ),
        evidence_ids=evidence_ids,
        notes=_notes(session, "finding", finding.id) if detail else [],
        retests=[public_retest(session, item) for item in retests] if detail else [],
        history=[
            HistoryResponse(
                id=event.id,
                event_type=event.event_type,
                summary=event.summary,
                details=event.details,
                created_at=event.created_at,
            )
            for event in events
        ]
        if detail
        else [],
        attack_chains=[
            RelatedAttackChainResponse(
                id=chain.id,
                display_id=chain.display_id,
                title=chain.title,
                status=chain.status,
            )
            for chain in attack_chains
        ],
    )


@router.get("/api/engagements/{engagement_id}/findings", response_model=list[FindingResponse])
def list_findings(
    engagement_id: str,
    session: SessionDep,
    severity: str | None = None,
    finding_status: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    retest: str | None = None,
    sort: str = "updated_desc",
) -> list[FindingResponse]:
    get_engagement_or_404(session, engagement_id)
    conditions = [Finding.engagement_id == engagement_id, Finding.archived_at.is_(None)]
    if severity:
        conditions.append(Finding.severity == severity)
    if finding_status:
        conditions.append(Finding.status == finding_status)
    if category:
        conditions.append(Finding.category == category)
    order = {
        "created_asc": Finding.created_at.asc(),
        "severity": Finding.severity.asc(),
        "id": Finding.sequence_number.asc(),
    }.get(sort, Finding.updated_at.desc())
    findings = list(session.scalars(select(Finding).where(*conditions).order_by(order)))
    response = [public_finding(session, item) for item in findings]
    if retest == "not_retested":
        response = [item for item in response if item.latest_retest is None]
    elif retest:
        response = [
            item for item in response if item.latest_retest and item.latest_retest.status == retest
        ]
    return response


@router.get(
    "/api/engagements/{engagement_id}/findings/{finding_id}", response_model=FindingResponse
)
def get_finding(engagement_id: str, finding_id: str, session: SessionDep) -> FindingResponse:
    return public_finding(session, _finding_or_404(session, engagement_id, finding_id))


@router.patch(
    "/api/engagements/{engagement_id}/findings/{finding_id}", response_model=FindingResponse
)
def update_finding(
    engagement_id: str, finding_id: str, payload: FindingUpdate, session: SessionDep
) -> FindingResponse:
    finding = _finding_or_404(session, engagement_id, finding_id)
    updates = payload.model_dump(exclude_unset=True)
    old_severity, old_status = finding.severity, finding.status
    for key, value in updates.items():
        if isinstance(value, str):
            value = redact_body(value) or ""
        elif isinstance(value, list):
            value = [redact_body(item) or "" for item in value]
        setattr(finding, key, value)
    if "severity" in updates and finding.severity != old_severity:
        add_history(
            session,
            finding.id,
            "severity_changed",
            f"Severity changed from {old_severity} to {finding.severity}",
            {"from": old_severity, "to": finding.severity},
        )
    if "status" in updates and finding.status != old_status:
        event_type = "finding_closed" if finding.status == "Closed" else "status_changed"
        add_history(
            session,
            finding.id,
            event_type,
            f"Status changed from {old_status} to {finding.status}",
            {"from": old_status, "to": finding.status},
        )
    session.commit()
    session.refresh(finding)
    return public_finding(session, finding)


@router.delete(
    "/api/engagements/{engagement_id}/findings/{finding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_finding(engagement_id: str, finding_id: str, session: SessionDep) -> None:
    finding = _finding_or_404(session, engagement_id, finding_id)
    finding.archived_at = datetime.now(UTC)
    add_history(session, finding.id, "finding_archived", "Finding archived")
    session.commit()


@router.post(
    "/api/engagements/{engagement_id}/evidence",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence(
    engagement_id: str, payload: EvidenceCreate, session: SessionDep
) -> EvidenceResponse:
    get_engagement_or_404(session, engagement_id)
    snapshot = _evidence_snapshot(session, engagement_id, payload)
    if payload.finding_id:
        _finding_or_404(session, engagement_id, payload.finding_id)
    if payload.source_candidate_id:
        _scoped_or_404(session, Candidate, engagement_id, payload.source_candidate_id, "Candidate")
    display_id, number = allocate_display_id(session, engagement_id, "evidence")
    item = Evidence(
        engagement_id=engagement_id,
        display_id=display_id,
        sequence_number=number,
        evidence_type=payload.evidence_type,
        title=redact_body(payload.title) or "Evidence",
        snapshot=snapshot,
        source_exchange_id=payload.source_exchange_id,
        source_comparison_id=payload.source_comparison_id,
        source_candidate_id=payload.source_candidate_id,
        finding_id=payload.finding_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return public_evidence(session, item)


@router.get("/api/engagements/{engagement_id}/evidence", response_model=list[EvidenceSummary])
def list_evidence(engagement_id: str, session: SessionDep) -> list[EvidenceSummary]:
    get_engagement_or_404(session, engagement_id)
    items = session.scalars(
        select(Evidence)
        .options(
            load_only(
                *(getattr(Evidence, name) for name in EvidenceSummary.model_fields), raiseload=True
            )
        )
        .where(Evidence.engagement_id == engagement_id)
        .order_by(Evidence.sequence_number.desc())
    )
    return [EvidenceSummary.model_validate(item) for item in items]


@router.get(
    "/api/engagements/{engagement_id}/evidence/{evidence_id}", response_model=EvidenceResponse
)
def get_evidence(engagement_id: str, evidence_id: str, session: SessionDep) -> EvidenceResponse:
    item = _scoped_or_404(session, Evidence, engagement_id, evidence_id, "Evidence")
    return public_evidence(session, item)


@router.post(
    "/api/engagements/{engagement_id}/findings/{finding_id}/retests",
    response_model=RetestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_retest(
    engagement_id: str,
    finding_id: str,
    payload: RetestCreate,
    session: SessionDep,
) -> RetestResponse:
    finding = _finding_or_404(session, engagement_id, finding_id)
    evidence = _evidence_for_retest(session, engagement_id, payload.evidence_ids, finding_id)
    display_id, number = allocate_display_id(session, engagement_id, "retest")
    item = Retest(
        engagement_id=engagement_id,
        finding_id=finding.id,
        display_id=display_id,
        sequence_number=number,
        status=payload.status,
        tested_at=payload.tested_at or datetime.now(UTC),
        operator_notes=redact_body(payload.operator_notes) or "",
    )
    session.add(item)
    session.flush()
    for evidence_item in evidence:
        session.execute(
            retest_evidence.insert().values(retest_id=item.id, evidence_id=evidence_item.id)
        )
    add_history(
        session,
        finding.id,
        "retest_added",
        f"{display_id} recorded as {item.status}",
        {"retest_id": display_id, "status": item.status},
    )
    status_for_result = {
        "Still Vulnerable": "In Remediation",
        "Partially Fixed": "In Remediation",
        "Fixed": "Fixed",
    }.get(item.status)
    if status_for_result and finding.status != status_for_result:
        previous_status = finding.status
        finding.status = status_for_result
        add_history(
            session,
            finding.id,
            "status_changed",
            f"Status changed from {previous_status} to {finding.status} after {display_id}",
            {"from": previous_status, "to": finding.status, "retest_id": display_id},
        )
    session.commit()
    session.refresh(item)
    return public_retest(session, item)


@router.patch("/api/engagements/{engagement_id}/retests/{retest_id}", response_model=RetestResponse)
def update_retest(
    engagement_id: str, retest_id: str, payload: RetestUpdate, session: SessionDep
) -> RetestResponse:
    item = _scoped_or_404(session, Retest, engagement_id, retest_id, "Retest")
    old_status = item.status
    updates = payload.model_dump(exclude_unset=True, exclude={"evidence_ids"})
    if "operator_notes" in updates:
        updates["operator_notes"] = redact_body(updates["operator_notes"]) or ""
    for key, value in updates.items():
        setattr(item, key, value)
    if payload.evidence_ids is not None:
        evidence = _evidence_for_retest(
            session, engagement_id, payload.evidence_ids, item.finding_id
        )
        session.execute(retest_evidence.delete().where(retest_evidence.c.retest_id == item.id))
        for evidence_item in evidence:
            session.execute(
                retest_evidence.insert().values(retest_id=item.id, evidence_id=evidence_item.id)
            )
    if item.status != old_status:
        add_history(
            session,
            item.finding_id,
            "retest_result_changed",
            f"{item.display_id} changed from {old_status} to {item.status}",
            {"retest_id": item.display_id, "from": old_status, "to": item.status},
        )
    session.commit()
    session.refresh(item)
    return public_retest(session, item)


@router.get("/api/engagements/{engagement_id}/retests", response_model=list[RetestResponse])
def list_retests(engagement_id: str, session: SessionDep) -> list[RetestResponse]:
    get_engagement_or_404(session, engagement_id)
    items = session.scalars(
        select(Retest)
        .where(Retest.engagement_id == engagement_id)
        .order_by(Retest.tested_at.desc())
    )
    return [public_retest(session, item) for item in items]


@router.post(
    "/api/engagements/{engagement_id}/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_note(engagement_id: str, payload: NoteCreate, session: SessionDep) -> NoteResponse:
    get_engagement_or_404(session, engagement_id)
    model = {
        "candidate": Candidate,
        "finding": Finding,
        "evidence": Evidence,
        "retest": Retest,
    }[payload.target_type]
    _scoped_or_404(session, model, engagement_id, payload.target_id, payload.target_type.title())
    note = OperatorNote(
        engagement_id=engagement_id,
        author_label="Operator",
        body=redact_body(payload.body) or "",
        **{f"{payload.target_type}_id": payload.target_id},
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return NoteResponse(
        id=note.id, author_label=note.author_label, body=note.body, created_at=note.created_at
    )


def _finding_or_404(session: Session, engagement_id: str, finding_id: str) -> Finding:
    finding = session.scalar(
        select(Finding).where(
            Finding.id == finding_id,
            Finding.engagement_id == engagement_id,
            Finding.archived_at.is_(None),
        )
    )
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return finding


def _scoped_or_404(session: Session, model: type, engagement_id: str, item_id: str, label: str):
    item = session.scalar(
        select(model).where(and_(model.id == item_id, model.engagement_id == engagement_id))
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return item


def _evidence_snapshot(
    session: Session, engagement_id: str, payload: EvidenceCreate
) -> dict[str, object]:
    if payload.evidence_type in {"HTTP Request/Response", "Replay"}:
        exchange = _scoped_or_404(
            session, HttpExchange, engagement_id, payload.source_exchange_id, "Request"
        )
        identity_name = None
        if exchange.identity_id:
            identity = session.get(Identity, exchange.identity_id)
            identity_name = identity.name if identity else None
        return redact_mapping(
            {
                "exchange": public_exchange(exchange).model_dump(mode="json"),
                "identity_name": identity_name,
            }
        )
    if payload.evidence_type == "Response Comparison":
        comparison = _scoped_or_404(
            session,
            ResponseComparison,
            engagement_id,
            payload.source_comparison_id,
            "Comparison",
        )
        replay_a = session.get(HttpExchange, comparison.replay_a_id)
        replay_b = session.get(HttpExchange, comparison.replay_b_id)
        identities = session.scalars(
            select(Identity).where(
                Identity.id.in_([comparison.identity_a_id, comparison.identity_b_id])
            )
        )
        identity_names = {identity.id: identity.name for identity in identities}
        return redact_mapping(
            {
                "comparison_id": comparison.id,
                "original_exchange_id": comparison.original_exchange_id,
                "identity_a": identity_names.get(comparison.identity_a_id),
                "identity_b": identity_names.get(comparison.identity_b_id),
                "result": comparison.result,
                "replay_a": public_exchange(replay_a).model_dump(mode="json") if replay_a else None,
                "replay_b": public_exchange(replay_b).model_dump(mode="json") if replay_b else None,
            }
        )
    return {"text": redact_body(payload.text) or ""}


def _evidence_for_retest(
    session: Session, engagement_id: str, evidence_ids: list[str], finding_id: str
) -> list[Evidence]:
    if not evidence_ids:
        return []
    evidence = list(
        session.scalars(
            select(Evidence).where(
                Evidence.engagement_id == engagement_id,
                Evidence.id.in_(set(evidence_ids)),
                Evidence.finding_id == finding_id,
            )
        )
    )
    if len(evidence) != len(set(evidence_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Retest evidence must belong to this finding and engagement",
        )
    return evidence
