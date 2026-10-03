from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from faultweaver.database import Base
from faultweaver.engagements.models import new_id, utc_now

candidate_replays = Table(
    "candidate_replays",
    Base.metadata,
    Column(
        "candidate_id",
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "exchange_id",
        String(36),
        ForeignKey("http_exchanges.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ResponseComparison(Base):
    __tablename__ = "response_comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    original_exchange_id: Mapped[str] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="CASCADE"), index=True
    )
    replay_a_id: Mapped[str] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="CASCADE"), index=True
    )
    replay_b_id: Mapped[str] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="CASCADE"), index=True
    )
    identity_a_id: Mapped[str] = mapped_column(
        ForeignKey("identities.id", ondelete="RESTRICT"), index=True
    )
    identity_b_id: Mapped[str] = mapped_column(
        ForeignKey("identities.id", ondelete="RESTRICT"), index=True
    )
    result: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("response_comparisons.id", ondelete="CASCADE"), unique=True
    )
    original_exchange_id: Mapped[str] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="candidate")
    review_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reasoning: Mapped[list[str]] = mapped_column(JSON)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    supporting_replays: Mapped[list[HttpExchange]] = relationship(secondary=candidate_replays)


from faultweaver.http_traffic.models import HttpExchange  # noqa: E402
