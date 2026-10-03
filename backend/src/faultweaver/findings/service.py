from sqlalchemy.orm import Session

from faultweaver.findings.models import EngagementSequence, FindingLifecycleEvent
from faultweaver.redaction import redact_body, redact_mapping


def allocate_display_id(session: Session, engagement_id: str, kind: str) -> tuple[str, int]:
    sequence = session.get(EngagementSequence, engagement_id)
    if sequence is None:
        sequence = EngagementSequence(engagement_id=engagement_id)
        session.add(sequence)
        session.flush()
    column, prefix = {
        "finding": ("next_finding", "FW"),
        "evidence": ("next_evidence", "EV"),
        "retest": ("next_retest", "RT"),
        "attack_chain": ("next_attack_chain", "AC"),
        "import": ("next_import", "IMP"),
    }[kind]
    number = getattr(sequence, column)
    setattr(sequence, column, number + 1)
    session.flush()
    return f"{prefix}-{number:03d}", number


def add_history(
    session: Session,
    finding_id: str,
    event_type: str,
    summary: str,
    details: dict[str, object] | None = None,
) -> FindingLifecycleEvent:
    event = FindingLifecycleEvent(
        finding_id=finding_id,
        event_type=event_type,
        summary=redact_body(summary) or "",
        details=redact_mapping(details or {}),
    )
    session.add(event)
    return event
