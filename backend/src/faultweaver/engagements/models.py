from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from faultweaver.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class EngagementStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    REPORTING = "reporting"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class Engagement(Base):
    __tablename__ = "engagements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default=EngagementStatus.DRAFT.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    scopes: Mapped[list[ScopeRule]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )
    exchanges: Mapped[list[HttpExchange]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )
    identities: Mapped[list[Identity]] = relationship(
        back_populates="engagement", cascade="all, delete-orphan"
    )


from faultweaver.http_traffic.models import HttpExchange  # noqa: E402
from faultweaver.identities.models import Identity  # noqa: E402
from faultweaver.scope.models import ScopeRule  # noqa: E402
