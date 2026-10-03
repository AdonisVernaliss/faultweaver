from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from faultweaver.database import Base
from faultweaver.engagements.models import new_id, utc_now


class EngagementSequence(Base):
    __tablename__ = "engagement_sequences"

    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), primary_key=True
    )
    next_finding: Mapped[int] = mapped_column(Integer, default=1)
    next_evidence: Mapped[int] = mapped_column(Integer, default=1)
    next_retest: Mapped[int] = mapped_column(Integer, default=1)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("engagement_id", "display_id", name="uq_finding_display_id"),
        UniqueConstraint("engagement_id", "sequence_number", name="uq_finding_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    display_id: Mapped[str] = mapped_column(String(24))
    sequence_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32), default="Open")
    affected_asset: Mapped[str] = mapped_column(String(500), default="")
    affected_endpoints: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    impact: Mapped[str] = mapped_column(Text, default="")
    reproduction_steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    remediation: Mapped[str] = mapped_column(Text, default="")
    references: Mapped[list[str]] = mapped_column(JSON, default=list)
    supporting_original_exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="SET NULL"), nullable=True
    )
    supporting_comparison_id: Mapped[str | None] = mapped_column(
        ForeignKey("response_comparisons.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("engagement_id", "display_id", name="uq_evidence_display_id"),
        UniqueConstraint("engagement_id", "sequence_number", name="uq_evidence_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    display_id: Mapped[str] = mapped_column(String(24))
    sequence_number: Mapped[int] = mapped_column(Integer)
    evidence_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    source_exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="SET NULL"), nullable=True
    )
    source_comparison_id: Mapped[str | None] = mapped_column(
        ForeignKey("response_comparisons.id", ondelete="SET NULL"), nullable=True
    )
    source_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True
    )
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    author_label: Mapped[str] = mapped_column(String(80), default="Operator")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Retest(Base):
    __tablename__ = "retests"
    __table_args__ = (
        UniqueConstraint("engagement_id", "display_id", name="uq_retest_display_id"),
        UniqueConstraint("engagement_id", "sequence_number", name="uq_retest_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), index=True
    )
    display_id: Mapped[str] = mapped_column(String(24))
    sequence_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    operator_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


retest_evidence = Table(
    "retest_evidence",
    Base.metadata,
    Column("retest_id", String(36), ForeignKey("retests.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "evidence_id", String(36), ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True
    ),
)


class OperatorNote(Base):
    __tablename__ = "operator_notes"
    __table_args__ = (
        CheckConstraint(
            "(candidate_id IS NOT NULL) + (finding_id IS NOT NULL) + "
            "(evidence_id IS NOT NULL) + (retest_id IS NOT NULL) = 1",
            name="ck_operator_note_one_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True
    )
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True
    )
    evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence.id", ondelete="RESTRICT"), nullable=True
    )
    retest_id: Mapped[str | None] = mapped_column(
        ForeignKey("retests.id", ondelete="RESTRICT"), nullable=True
    )
    author_label: Mapped[str] = mapped_column(String(80), default="Operator")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FindingLifecycleEvent(Base):
    __tablename__ = "finding_lifecycle_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(48))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
