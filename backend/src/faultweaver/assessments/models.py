from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from faultweaver.database import Base
from faultweaver.engagements.models import new_id, utc_now


class AssessmentRun(Base):
    __tablename__ = "assessment_runs"
    __table_args__ = (
        UniqueConstraint("engagement_id", "display_id", name="uq_assessment_run_display_id"),
        UniqueConstraint("engagement_id", "sequence_number", name="uq_assessment_run_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    display_id: Mapped[str] = mapped_column(String(24))
    sequence_number: Mapped[int] = mapped_column(Integer)
    target_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), index=True, default="Pending")
    max_pages: Mapped[int] = mapped_column(Integer)
    max_depth: Mapped[int] = mapped_column(Integer)
    max_requests: Mapped[int] = mapped_column(Integer)
    requests_per_second: Mapped[float] = mapped_column(Float)
    concurrency: Mapped[int] = mapped_column(Integer)
    request_timeout_seconds: Mapped[float] = mapped_column(Float)
    max_response_bytes: Mapped[int] = mapped_column(Integer)
    max_query_variants_per_path: Mapped[int] = mapped_column(Integer)
    inspect_site_metadata: Mapped[bool] = mapped_column(Boolean, default=True)
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    resource_count: Mapped[int] = mapped_column(Integer, default=0)
    endpoint_count: Mapped[int] = mapped_column(Integer, default=0)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_request_count: Mapped[int] = mapped_column(Integer, default=0)
    queued_count: Mapped[int] = mapped_column(Integer, default=0)
    current_depth: Mapped[int] = mapped_column(Integer, default=0)
    current_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CrawlDiscovery(Base):
    __tablename__ = "crawl_discoveries"
    __table_args__ = (
        UniqueConstraint("assessment_run_id", "canonical_url", name="uq_crawl_discovery_url"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_run_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_runs.id", ondelete="CASCADE"), index=True
    )
    parent_exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)
    depth: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(24), index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CrawlForm(Base):
    __tablename__ = "crawl_forms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_run_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_runs.id", ondelete="CASCADE"), index=True
    )
    exchange_id: Mapped[str] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="CASCADE"), index=True
    )
    action_url: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(16))
    enctype: Mapped[str] = mapped_column(String(120))
    fields: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BaselineObservation(Base):
    __tablename__ = "baseline_observations"
    __table_args__ = (
        UniqueConstraint("assessment_run_id", "fingerprint", name="uq_baseline_observation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_run_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_runs.id", ondelete="CASCADE"), index=True
    )
    exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    endpoint_id: Mapped[str | None] = mapped_column(
        ForeignKey("attack_surface_endpoints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    check_id: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16))
    classification: Mapped[str] = mapped_column(String(24), index=True)
    suggested_severity: Mapped[str] = mapped_column(String(24))
    fingerprint: Mapped[str] = mapped_column(String(200))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    affected_exchange_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
