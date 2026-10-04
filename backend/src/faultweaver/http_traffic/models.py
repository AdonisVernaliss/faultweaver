from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from faultweaver.database import Base
from faultweaver.engagements.models import new_id, utc_now


class HttpExchange(Base):
    __tablename__ = "http_exchanges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    parent_exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    identity_id: Mapped[str | None] = mapped_column(
        ForeignKey("identities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    endpoint_id: Mapped[str | None] = mapped_column(
        ForeignKey("attack_surface_endpoints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assessment_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("assessment_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    discovered_from_exchange_id: Mapped[str | None] = mapped_column(
        ForeignKey("http_exchanges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    crawl_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    crawl_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_entry_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auth_source: Mapped[str] = mapped_column(String(24), default="original")
    operator_modified: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(16), index=True)
    url: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(String(253), index=True)
    path: Mapped[str] = mapped_column(Text, index=True)
    query: Mapped[str] = mapped_column(Text, default="")
    request_headers: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    response_headers: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    redirect_chain: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    engagement: Mapped[Engagement] = relationship(back_populates="exchanges")
    parent: Mapped[HttpExchange | None] = relationship(
        remote_side=[id], foreign_keys=[parent_exchange_id]
    )
    identity: Mapped[Identity | None] = relationship()


from faultweaver.engagements.models import Engagement  # noqa: E402
from faultweaver.identities.models import Identity  # noqa: E402
