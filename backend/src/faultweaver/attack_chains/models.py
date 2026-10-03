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


class AttackChain(Base):
    __tablename__ = "attack_chains"
    __table_args__ = (
        UniqueConstraint("engagement_id", "display_id", name="uq_attack_chain_display_id"),
        UniqueConstraint("engagement_id", "sequence_number", name="uq_attack_chain_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    display_id: Mapped[str] = mapped_column(String(24))
    sequence_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    resulting_impact: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="Draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttackChainStep(Base):
    __tablename__ = "attack_chain_steps"
    __table_args__ = (
        UniqueConstraint("attack_chain_id", "position", name="uq_attack_chain_step_position"),
        CheckConstraint(
            "(step_type = 'Finding' AND finding_id IS NOT NULL) OR "
            "(step_type = 'Intermediate' AND finding_id IS NULL)",
            name="ck_attack_chain_step_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attack_chain_id: Mapped[str] = mapped_column(
        ForeignKey("attack_chains.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    step_type: Mapped[str] = mapped_column(String(24))
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


attack_chain_evidence = Table(
    "attack_chain_evidence",
    Base.metadata,
    Column(
        "attack_chain_id",
        String(36),
        ForeignKey("attack_chains.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "evidence_id",
        String(36),
        ForeignKey("evidence.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)


attack_chain_step_evidence = Table(
    "attack_chain_step_evidence",
    Base.metadata,
    Column(
        "step_id",
        String(36),
        ForeignKey("attack_chain_steps.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "evidence_id",
        String(36),
        ForeignKey("evidence.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)


class AttackChainHistoryEvent(Base):
    __tablename__ = "attack_chain_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attack_chain_id: Mapped[str] = mapped_column(
        ForeignKey("attack_chains.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(48))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
