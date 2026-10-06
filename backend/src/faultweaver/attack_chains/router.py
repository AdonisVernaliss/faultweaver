from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, load_only

from faultweaver.attack_chains.models import (
    AttackChain,
    AttackChainHistoryEvent,
    AttackChainStep,
    attack_chain_evidence,
    attack_chain_step_evidence,
)
from faultweaver.attack_chains.schemas import (
    AttackChainCreate,
    AttackChainEvidenceLink,
    AttackChainEvidenceResponse,
    AttackChainFindingResponse,
    AttackChainHistoryResponse,
    AttackChainReorder,
    AttackChainResponse,
    AttackChainStepCreate,
    AttackChainStepResponse,
    AttackChainStepUpdate,
    AttackChainUpdate,
)
from faultweaver.attack_chains.service import (
    add_attack_chain_history,
    assign_positions,
    ordered_steps,
    return_to_draft,
    validate_chain_integrity,
)
from faultweaver.database import get_session
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.findings.models import Evidence, Finding
from faultweaver.findings.service import allocate_display_id
from faultweaver.redaction import redact_body

router = APIRouter(tags=["attack-chains"])
SessionDep = Annotated[Session, Depends(get_session)]


def _evidence_response(item: Evidence) -> AttackChainEvidenceResponse:
    return AttackChainEvidenceResponse(
        id=item.id,
        display_id=item.display_id,
        title=item.title,
        evidence_type=item.evidence_type,
        captured_at=item.captured_at,
    )


def public_attack_chain(session: Session, chain: AttackChain) -> AttackChainResponse:
    steps = ordered_steps(session, chain.id)
    finding_ids = {step.finding_id for step in steps if step.finding_id is not None}
    findings = {
        finding.id: finding
        for finding in session.scalars(select(Finding).where(Finding.id.in_(finding_ids)))
    }
    chain_evidence = list(
        session.scalars(
            select(Evidence)
            .options(
                load_only(
                    Evidence.id,
                    Evidence.display_id,
                    Evidence.title,
                    Evidence.evidence_type,
                    Evidence.captured_at,
                    raiseload=True,
                )
            )
            .join(attack_chain_evidence, attack_chain_evidence.c.evidence_id == Evidence.id)
            .where(attack_chain_evidence.c.attack_chain_id == chain.id)
            .order_by(Evidence.sequence_number)
        )
    )
    step_evidence_rows = session.execute(
        select(attack_chain_step_evidence.c.step_id, Evidence)
        .options(
            load_only(
                Evidence.id,
                Evidence.display_id,
                Evidence.title,
                Evidence.evidence_type,
                Evidence.captured_at,
                raiseload=True,
            )
        )
        .join(Evidence, attack_chain_step_evidence.c.evidence_id == Evidence.id)
        .where(attack_chain_step_evidence.c.step_id.in_([step.id for step in steps]))
        .order_by(Evidence.sequence_number)
    ).all()
    evidence_by_step: dict[str, list[Evidence]] = {}
    for step_id, evidence in step_evidence_rows:
        evidence_by_step.setdefault(step_id, []).append(evidence)
    history = list(
        session.scalars(
            select(AttackChainHistoryEvent)
            .where(AttackChainHistoryEvent.attack_chain_id == chain.id)
            .order_by(AttackChainHistoryEvent.created_at)
        )
    )
    severity_composition: dict[str, int] = {}
    for finding in findings.values():
        severity_composition[finding.severity] = severity_composition.get(finding.severity, 0) + 1
    return AttackChainResponse(
        id=chain.id,
        engagement_id=chain.engagement_id,
        display_id=chain.display_id,
        title=chain.title,
        description=chain.description,
        resulting_impact=chain.resulting_impact,
        status=chain.status,
        steps=[
            _public_step(step, findings.get(step.finding_id), evidence_by_step.get(step.id, []))
            for step in steps
        ],
        evidence=[_evidence_response(item) for item in chain_evidence],
        finding_count=len(finding_ids),
        severity_composition=severity_composition,
        history=[
            AttackChainHistoryResponse(
                id=item.id,
                event_type=item.event_type,
                summary=item.summary,
                details=item.details,
                created_at=item.created_at,
            )
            for item in history
        ],
        created_at=chain.created_at,
        updated_at=chain.updated_at,
        archived_at=chain.archived_at,
    )


@router.post(
    "/api/engagements/{engagement_id}/attack-chains",
    response_model=AttackChainResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_attack_chain(
    engagement_id: str, payload: AttackChainCreate, session: SessionDep
) -> AttackChainResponse:
    get_engagement_or_404(session, engagement_id)
    display_id, number = allocate_display_id(session, engagement_id, "attack_chain")
    chain = AttackChain(
        engagement_id=engagement_id,
        display_id=display_id,
        sequence_number=number,
        title=redact_body(payload.title.strip()) or "Attack chain",
        description=redact_body(payload.description) or "",
        resulting_impact=redact_body(payload.resulting_impact) or "",
        status="Draft",
    )
    session.add(chain)
    session.flush()
    add_attack_chain_history(
        session,
        chain.id,
        "attack_chain_created",
        f"Attack chain {display_id} created",
        {"attack_chain_id": display_id},
    )
    session.commit()
    session.refresh(chain)
    return public_attack_chain(session, chain)


@router.get(
    "/api/engagements/{engagement_id}/attack-chains",
    response_model=list[AttackChainResponse],
)
def list_attack_chains(
    engagement_id: str,
    session: SessionDep,
    chain_status: str | None = Query(default=None, alias="status"),
    finding_id: str | None = None,
    search: str | None = None,
) -> list[AttackChainResponse]:
    get_engagement_or_404(session, engagement_id)
    statement = select(AttackChain).where(AttackChain.engagement_id == engagement_id)
    if chain_status:
        statement = statement.where(AttackChain.status == chain_status)
    else:
        statement = statement.where(AttackChain.status != "Archived")
    if search:
        needle = f"%{search.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(AttackChain.title).like(needle),
                func.lower(AttackChain.display_id).like(needle),
            )
        )
    if finding_id:
        statement = statement.join(AttackChainStep).where(AttackChainStep.finding_id == finding_id)
    chains = session.scalars(statement.order_by(AttackChain.updated_at.desc())).unique()
    return [public_attack_chain(session, chain) for chain in chains]


@router.get(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}",
    response_model=AttackChainResponse,
)
def get_attack_chain(engagement_id: str, chain_id: str, session: SessionDep) -> AttackChainResponse:
    return public_attack_chain(session, _chain_or_404(session, engagement_id, chain_id))


@router.patch(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}",
    response_model=AttackChainResponse,
)
def update_attack_chain(
    engagement_id: str,
    chain_id: str,
    payload: AttackChainUpdate,
    session: SessionDep,
) -> AttackChainResponse:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    updates = payload.model_dump(exclude_unset=True)
    old_status = chain.status
    content_changed = any(
        field in updates for field in ("title", "description", "resulting_impact")
    )
    for field, value in updates.items():
        setattr(chain, field, redact_body(value) or "" if field != "status" else value)
    if updates.get("status") == "Validated":
        try:
            validate_chain_integrity(session, chain)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
            ) from error
    elif content_changed:
        return_to_draft(session, chain, "chain content changed")
    drafted_by_content_change = (
        content_changed and old_status == "Validated" and "status" not in updates
    )
    if chain.status != old_status and not drafted_by_content_change:
        add_attack_chain_history(
            session,
            chain.id,
            "status_changed",
            f"Status changed from {old_status} to {chain.status}",
            {"from": old_status, "to": chain.status},
        )
    session.commit()
    session.refresh(chain)
    return public_attack_chain(session, chain)


@router.delete(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_attack_chain(engagement_id: str, chain_id: str, session: SessionDep) -> None:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    previous = chain.status
    chain.status = "Archived"
    chain.archived_at = datetime.now(UTC)
    add_attack_chain_history(
        session,
        chain.id,
        "attack_chain_archived",
        f"Attack chain archived from {previous}",
        {"from": previous, "to": "Archived"},
    )
    session.commit()


@router.post(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}/steps",
    response_model=AttackChainResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_attack_chain_step(
    engagement_id: str,
    chain_id: str,
    payload: AttackChainStepCreate,
    session: SessionDep,
) -> AttackChainResponse:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    finding = None
    if payload.finding_id:
        finding = _finding_or_404(session, engagement_id, payload.finding_id)
    steps = ordered_steps(session, chain.id)
    insert_at = min(payload.position or len(steps) + 1, len(steps) + 1) - 1
    step = AttackChainStep(
        attack_chain_id=chain.id,
        position=0,
        step_type=payload.step_type,
        finding_id=finding.id if finding else None,
        title=redact_body(payload.title.strip()) or "",
        description=redact_body(payload.description) or "",
    )
    session.add(step)
    session.flush()
    steps.insert(insert_at, step)
    assign_positions(session, steps)
    chain.updated_at = datetime.now(UTC)
    return_to_draft(session, chain, "step added")
    if finding:
        event_type = "finding_added"
        summary = f"{finding.display_id} added at step {step.position}"
        details = {"finding_id": finding.display_id, "step_id": step.id}
    else:
        event_type = "intermediate_step_added"
        summary = f"Intermediate step added at position {step.position}"
        details = {"step_id": step.id}
    add_attack_chain_history(session, chain.id, event_type, summary, details)
    session.commit()
    session.refresh(chain)
    return public_attack_chain(session, chain)


@router.patch(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}/steps/{step_id}",
    response_model=AttackChainResponse,
)
def update_attack_chain_step(
    engagement_id: str,
    chain_id: str,
    step_id: str,
    payload: AttackChainStepUpdate,
    session: SessionDep,
) -> AttackChainResponse:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    step = _step_or_404(session, chain.id, step_id)
    updates = payload.model_dump(exclude_unset=True)
    if step.step_type == "Intermediate" and "title" in updates and not updates["title"].strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Intermediate steps require a title",
        )
    for field, value in updates.items():
        setattr(step, field, redact_body(value) or "")
    chain.updated_at = datetime.now(UTC)
    return_to_draft(session, chain, "step content changed")
    session.commit()
    session.refresh(chain)
    return public_attack_chain(session, chain)


@router.delete(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}/steps/{step_id}",
    response_model=AttackChainResponse,
)
def remove_attack_chain_step(
    engagement_id: str, chain_id: str, step_id: str, session: SessionDep
) -> AttackChainResponse:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    step = _step_or_404(session, chain.id, step_id)
    finding = session.get(Finding, step.finding_id) if step.finding_id else None
    session.delete(step)
    session.flush()
    remaining = ordered_steps(session, chain.id)
    assign_positions(session, remaining)
    chain.updated_at = datetime.now(UTC)
    return_to_draft(session, chain, "step removed")
    event_type = "finding_removed" if finding else "step_removed"
    summary = (
        f"{finding.display_id} removed from attack chain"
        if finding
        else "Intermediate step removed from attack chain"
    )
    add_attack_chain_history(session, chain.id, event_type, summary, {"step_id": step_id})
    session.commit()
    session.refresh(chain)
    return public_attack_chain(session, chain)


@router.put(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}/steps/order",
    response_model=AttackChainResponse,
)
def reorder_attack_chain_steps(
    engagement_id: str,
    chain_id: str,
    payload: AttackChainReorder,
    session: SessionDep,
) -> AttackChainResponse:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    steps = ordered_steps(session, chain.id)
    if len(payload.ordered_step_ids) != len(set(payload.ordered_step_ids)) or set(
        payload.ordered_step_ids
    ) != {step.id for step in steps}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ordered step IDs must contain every chain step exactly once",
        )
    by_id = {step.id: step for step in steps}
    assign_positions(session, [by_id[step_id] for step_id in payload.ordered_step_ids])
    chain.updated_at = datetime.now(UTC)
    return_to_draft(session, chain, "steps reordered")
    add_attack_chain_history(
        session,
        chain.id,
        "steps_reordered",
        "Attack chain steps reordered",
        {"ordered_step_ids": payload.ordered_step_ids},
    )
    session.commit()
    session.refresh(chain)
    return public_attack_chain(session, chain)


@router.post(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}/evidence",
    response_model=AttackChainResponse,
)
def attach_chain_evidence(
    engagement_id: str,
    chain_id: str,
    payload: AttackChainEvidenceLink,
    session: SessionDep,
) -> AttackChainResponse:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    evidence = _evidence_or_404(session, engagement_id, payload.evidence_id)
    try:
        session.execute(
            insert(attack_chain_evidence).values(attack_chain_id=chain.id, evidence_id=evidence.id)
        )
        add_attack_chain_history(
            session,
            chain.id,
            "evidence_attached",
            f"{evidence.display_id} attached to attack chain",
            {"evidence_id": evidence.display_id},
        )
        chain.updated_at = datetime.now(UTC)
        session.commit()
    except IntegrityError:
        session.rollback()
    return public_attack_chain(session, chain)


@router.delete(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}/evidence/{evidence_id}",
    response_model=AttackChainResponse,
)
def detach_chain_evidence(
    engagement_id: str,
    chain_id: str,
    evidence_id: str,
    session: SessionDep,
) -> AttackChainResponse:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    evidence = _evidence_or_404(session, engagement_id, evidence_id)
    result = session.execute(
        delete(attack_chain_evidence).where(
            attack_chain_evidence.c.attack_chain_id == chain.id,
            attack_chain_evidence.c.evidence_id == evidence.id,
        )
    )
    if result.rowcount:
        add_attack_chain_history(
            session,
            chain.id,
            "evidence_detached",
            f"{evidence.display_id} detached from attack chain",
            {"evidence_id": evidence.display_id},
        )
        chain.updated_at = datetime.now(UTC)
    session.commit()
    return public_attack_chain(session, chain)


@router.post(
    "/api/engagements/{engagement_id}/attack-chains/{chain_id}/steps/{step_id}/evidence",
    response_model=AttackChainResponse,
)
def attach_step_evidence(
    engagement_id: str,
    chain_id: str,
    step_id: str,
    payload: AttackChainEvidenceLink,
    session: SessionDep,
) -> AttackChainResponse:
    chain = _active_chain_or_404(session, engagement_id, chain_id)
    step = _step_or_404(session, chain.id, step_id)
    evidence = _evidence_or_404(session, engagement_id, payload.evidence_id)
    try:
        session.execute(
            insert(attack_chain_step_evidence).values(step_id=step.id, evidence_id=evidence.id)
        )
        add_attack_chain_history(
            session,
            chain.id,
            "evidence_attached",
            f"{evidence.display_id} attached to step {step.position}",
            {"evidence_id": evidence.display_id, "step_id": step.id},
        )
        chain.updated_at = datetime.now(UTC)
        session.commit()
    except IntegrityError:
        session.rollback()
    return public_attack_chain(session, chain)


def _public_step(
    step: AttackChainStep, finding: Finding | None, evidence: list[Evidence]
) -> AttackChainStepResponse:
    finding_response = (
        AttackChainFindingResponse(
            id=finding.id,
            display_id=finding.display_id,
            title=finding.title,
            severity=finding.severity,
            status=finding.status,
        )
        if finding
        else None
    )
    return AttackChainStepResponse(
        id=step.id,
        position=step.position,
        step_type=step.step_type,
        finding_id=step.finding_id,
        title=finding.title if finding and not step.title else step.title,
        description=step.description,
        finding=finding_response,
        evidence=[_evidence_response(item) for item in evidence],
        created_at=step.created_at,
        updated_at=step.updated_at,
    )


def _chain_or_404(session: Session, engagement_id: str, chain_id: str) -> AttackChain:
    chain = session.scalar(
        select(AttackChain).where(
            AttackChain.id == chain_id, AttackChain.engagement_id == engagement_id
        )
    )
    if chain is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attack chain not found")
    return chain


def _active_chain_or_404(session: Session, engagement_id: str, chain_id: str) -> AttackChain:
    chain = _chain_or_404(session, engagement_id, chain_id)
    if chain.status == "Archived":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attack chain is archived")
    return chain


def _step_or_404(session: Session, chain_id: str, step_id: str) -> AttackChainStep:
    step = session.scalar(
        select(AttackChainStep).where(
            AttackChainStep.id == step_id, AttackChainStep.attack_chain_id == chain_id
        )
    )
    if step is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attack chain step not found"
        )
    return step


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


def _evidence_or_404(session: Session, engagement_id: str, evidence_id: str) -> Evidence:
    evidence = session.scalar(
        select(Evidence).where(Evidence.id == evidence_id, Evidence.engagement_id == engagement_id)
    )
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    return evidence
