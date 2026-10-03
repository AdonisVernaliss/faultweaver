from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from faultweaver.database import Base
from faultweaver.engagements.models import new_id, utc_now


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("engagement_id", "display_id", name="uq_import_batch_display_id"),
        UniqueConstraint("engagement_id", "sequence_number", name="uq_import_batch_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    display_id: Mapped[str] = mapped_column(String(24))
    sequence_number: Mapped[int] = mapped_column(Integer)
    import_format: Mapped[str] = mapped_column(String(24), index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_digest: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24))
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    new_endpoint_count: Mapped[int] = mapped_column(Integer, default=0)
    known_endpoint_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AttackSurfaceEndpoint(Base):
    __tablename__ = "attack_surface_endpoints"
    __table_args__ = (
        UniqueConstraint("engagement_id", "canonical_key", name="uq_attack_surface_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    canonical_key: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(16), index=True)
    scheme: Mapped[str | None] = mapped_column(String(12), nullable=True)
    host: Mapped[str | None] = mapped_column(String(253), nullable=True, index=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    path_template: Mapped[str] = mapped_column(Text, index=True)
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    declared_by_openapi: Mapped[bool] = mapped_column(default=False)
    details: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
