from __future__ import annotations

from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from faultweaver.assessments.urls import InvalidCrawlUrl, canonicalize_url


class AssessmentCreate(BaseModel):
    target_url: AnyHttpUrl
    max_pages: int = Field(default=50, ge=1, le=500)
    max_depth: int = Field(default=3, ge=0, le=10)
    max_requests: int = Field(default=75, ge=1, le=1_000)
    requests_per_second: float = Field(default=1.0, ge=0.1, le=20)
    concurrency: int = Field(default=2, ge=1, le=8)
    request_timeout_seconds: float = Field(default=10.0, ge=1, le=60)
    max_response_bytes: int = Field(default=1_000_000, ge=1_024, le=10_000_000)
    max_query_variants_per_path: int = Field(default=3, ge=1, le=25)
    inspect_site_metadata: bool = True

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        try:
            canonicalize_url(str(value))
        except InvalidCrawlUrl as error:
            raise ValueError(str(error)) from error
        return value


class AssessmentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    engagement_id: str
    display_id: str
    target_url: str
    status: str
    max_pages: int
    max_depth: int
    max_requests: int
    requests_per_second: float
    concurrency: int
    request_timeout_seconds: float
    max_response_bytes: int
    max_query_variants_per_path: int
    inspect_site_metadata: bool
    stop_requested: bool
    request_count: int
    page_count: int
    resource_count: int
    endpoint_count: int
    observation_count: int
    candidate_count: int
    failed_request_count: int
    queued_count: int
    current_depth: int
    current_url: str | None
    warnings: list[str]
    stop_reason: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class DiscoveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_exchange_id: str | None
    requested_exchange_id: str | None
    url: str
    canonical_url: str
    depth: int
    kind: str
    state: str
    reason: str | None


class FormResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exchange_id: str
    action_url: str
    method: str
    enctype: str
    fields: list[dict[str, object]]


class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exchange_id: str | None
    endpoint_id: str | None
    candidate_id: str | None
    check_id: str
    title: str
    description: str
    reason: str
    confidence: str
    classification: str
    suggested_severity: str
    occurrence_count: int
    affected_exchange_ids: list[str]
    details: dict[str, object]


class AssessmentDetail(AssessmentSummary):
    discoveries: list[DiscoveryResponse]
    forms: list[FormResponse]
    observations: list[ObservationResponse]
    request_ids: list[str]
    candidate_ids: list[str]
