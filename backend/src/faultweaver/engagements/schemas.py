from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from faultweaver.engagements.models import EngagementStatus


class EngagementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10_000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class EngagementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    status: EngagementStatus
    created_at: datetime
    updated_at: datetime


class EngagementDetail(EngagementResponse):
    scope_count: int
    request_count: int
