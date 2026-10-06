from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from faultweaver.http_traffic.schemas import ExchangeResponse


class ComparisonCreate(BaseModel):
    identity_a_id: str
    identity_b_id: str

    @model_validator(mode="after")
    def identities_are_distinct(self) -> "ComparisonCreate":
        if self.identity_a_id == self.identity_b_id:
            raise ValueError("Comparison identities must be distinct")
        return self


class CandidateSummary(BaseModel):
    id: str
    engagement_id: str
    comparison_id: str | None
    original_exchange_id: str
    assessment_run_id: str | None
    endpoint_id: str | None
    check_id: str | None
    suggested_severity: str | None
    affected_exchange_ids: list[str]
    supporting_replay_ids: list[str]
    title: str
    category: str
    confidence: str
    status: str
    review_decision: str | None
    reviewed_at: datetime | None
    archived_at: datetime | None
    finding_id: str | None
    reasoning: list[str]
    notes: str
    target: dict[str, str]
    identities: list[dict[str, str]]
    response_statuses: list[dict[str, object]]
    operator_notes: list[dict[str, object]]
    created_at: datetime
    updated_at: datetime


class CandidateResponse(CandidateSummary):
    original: ExchangeResponse | None
    supporting_replays: list[ExchangeResponse]
    comparison_result: dict[str, object]


class CandidateUpdate(BaseModel):
    status: Literal["candidate", "confirmed", "rejected"] | None = None
    notes: str | None = Field(default=None, max_length=20_000)


class CandidateReview(BaseModel):
    decision: Literal["False Positive", "Informational", "Accepted"]
    note: str = Field(default="", max_length=20_000)


class ComparisonResponse(BaseModel):
    id: str
    engagement_id: str
    original_exchange_id: str
    replay_a: ExchangeResponse
    replay_b: ExchangeResponse
    identity_a_id: str
    identity_b_id: str
    result: dict[str, object]
    candidate: CandidateResponse | None
    created_at: datetime


class AuthorizationMatrixCell(BaseModel):
    state: Literal["observed", "missing_response", "not_tested"]
    status: int | None = None
    evidence_request_id: str | None = None


class AuthorizationMatrixRow(BaseModel):
    method: str
    host: str
    path: str
    original_request_id: str
    cells: dict[str, AuthorizationMatrixCell]


class AuthorizationMatrixIdentity(BaseModel):
    id: str
    name: str
    is_anonymous: bool


class AuthorizationMatrixResponse(BaseModel):
    identities: list[AuthorizationMatrixIdentity]
    rows: list[AuthorizationMatrixRow]
