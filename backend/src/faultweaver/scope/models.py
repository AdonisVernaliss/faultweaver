from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from faultweaver.database import Base
from faultweaver.engagements.models import new_id


class ScopeRule(Base):
    __tablename__ = "scope_rules"
    __table_args__ = (
        UniqueConstraint(
            "engagement_id",
            "scheme",
            "hostname",
            "port",
            "path_prefix",
            name="uq_scope_rule",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    scheme: Mapped[str] = mapped_column(String(8))
    hostname: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(Integer)
    path_prefix: Mapped[str] = mapped_column(String(2048), default="/")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    engagement: Mapped[Engagement] = relationship(back_populates="scopes")


from faultweaver.engagements.models import Engagement  # noqa: E402
