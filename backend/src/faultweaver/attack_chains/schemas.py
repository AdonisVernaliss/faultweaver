from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

AttackChainStatus = Literal["Draft", "Validated", "Archived"]
AttackChainStepType = Literal["Finding", "Intermediate"]


class AttackChainCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=100_000)
    resulting_impact: str = Field(default="", max_length=100_000)


class AttackChainUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=100_000)
    resulting_impact: str | None = Field(default=None, max_length=100_000)
    status: Literal["Draft", "Validated"] | None = None


class AttackChainStepCreate(BaseModel):
    step_type: AttackChainStepType
    finding_id: str | None = None
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=100_000)
    position: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_step_target(self) -> "AttackChainStepCreate":
        if self.step_type == "Finding" and self.finding_id is None:
            raise ValueError("finding_id is required for a Finding step")
        if self.step_type == "Intermediate" and self.finding_id is not None:
            raise ValueError("Intermediate steps cannot reference a Finding")
        if self.step_type == "Intermediate" and not self.title.strip():
            raise ValueError("Intermediate steps require a title")
        return self


class AttackChainStepUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=100_000)


class AttackChainReorder(BaseModel):
    ordered_step_ids: list[str] = Field(min_length=1, max_length=200)


class AttackChainEvidenceLink(BaseModel):
    evidence_id: str


class AttackChainFindingResponse(BaseModel):
    id: str
    display_id: str
    title: str
    severity: str
    status: str


class AttackChainEvidenceResponse(BaseModel):
    id: str
    display_id: str
    title: str
    evidence_type: str
    captured_at: datetime


class AttackChainStepResponse(BaseModel):
    id: str
    position: int
    step_type: str
    finding_id: str | None
    title: str
    description: str
    finding: AttackChainFindingResponse | None
    evidence: list[AttackChainEvidenceResponse]
    created_at: datetime
    updated_at: datetime


class AttackChainHistoryResponse(BaseModel):
    id: str
    event_type: str
    summary: str
    details: dict[str, object]
    created_at: datetime


class AttackChainResponse(BaseModel):
    id: str
    engagement_id: str
    display_id: str
    title: str
    description: str
    resulting_impact: str
    status: str
    steps: list[AttackChainStepResponse]
    evidence: list[AttackChainEvidenceResponse]
    finding_count: int
    severity_composition: dict[str, int]
    history: list[AttackChainHistoryResponse]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
