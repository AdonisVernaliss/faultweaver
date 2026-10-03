from sqlalchemy import select
from sqlalchemy.orm import Session

from faultweaver.attack_chains.models import (
    AttackChain,
    AttackChainHistoryEvent,
    AttackChainStep,
)
from faultweaver.findings.models import Finding
from faultweaver.redaction import redact_body, redact_mapping


def add_attack_chain_history(
    session: Session,
    chain_id: str,
    event_type: str,
    summary: str,
    details: dict[str, object] | None = None,
) -> AttackChainHistoryEvent:
    event = AttackChainHistoryEvent(
        attack_chain_id=chain_id,
        event_type=event_type,
        summary=redact_body(summary) or "",
        details=redact_mapping(details or {}),
    )
    session.add(event)
    return event


def ordered_steps(session: Session, chain_id: str) -> list[AttackChainStep]:
    return list(
        session.scalars(
            select(AttackChainStep)
            .where(AttackChainStep.attack_chain_id == chain_id)
            .order_by(AttackChainStep.position)
        )
    )


def assign_positions(session: Session, steps: list[AttackChainStep]) -> None:
    for offset, step in enumerate(steps, start=1):
        step.position = -offset
    session.flush()
    for position, step in enumerate(steps, start=1):
        step.position = position
    session.flush()


def validate_chain_integrity(session: Session, chain: AttackChain) -> None:
    steps = ordered_steps(session, chain.id)
    if not chain.title.strip():
        raise ValueError("Attack chain requires a title")
    if len(steps) < 2:
        raise ValueError("Attack chain requires at least two meaningful steps")
    if [step.position for step in steps] != list(range(1, len(steps) + 1)):
        raise ValueError("Attack chain step ordering is invalid")
    for step in steps:
        if step.step_type == "Intermediate" and not step.title.strip():
            raise ValueError("Intermediate steps require a title")
        if step.step_type == "Finding":
            finding = session.get(Finding, step.finding_id)
            if (
                finding is None
                or finding.engagement_id != chain.engagement_id
                or finding.archived_at is not None
            ):
                raise ValueError("Referenced finding is unavailable for validation")


def return_to_draft(session: Session, chain: AttackChain, reason: str) -> None:
    if chain.status != "Validated":
        return
    chain.status = "Draft"
    add_attack_chain_history(
        session,
        chain.id,
        "status_changed",
        f"Status changed from Validated to Draft after {reason}",
        {"from": "Validated", "to": "Draft", "reason": reason},
    )
