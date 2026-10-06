from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from faultweaver.database import Base
from faultweaver.engagements.models import new_id, utc_now


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("engagement_id", "display_id", name="uq_report_display_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    display_id: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default="Draft")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    revision_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportRevision(Base):
    __tablename__ = "report_revisions"
    __table_args__ = (UniqueConstraint("report_id", "revision", name="uq_report_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(String(16))
    document_sha256: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict] = mapped_column(JSON)
