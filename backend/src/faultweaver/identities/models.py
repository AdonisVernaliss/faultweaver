from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from faultweaver.database import Base
from faultweaver.engagements.models import new_id, utc_now


class Identity(Base):
    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("engagement_id", "name", name="uq_identity_engagement_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    bearer_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_header: Mapped[str | None] = mapped_column(String(160), nullable=True)
    api_key_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    cookies: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    custom_headers: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    engagement: Mapped[Engagement] = relationship(back_populates="identities")


from faultweaver.engagements.models import Engagement  # noqa: E402
