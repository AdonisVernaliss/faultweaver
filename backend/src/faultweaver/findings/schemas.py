from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["Critical", "High", "Medium", "Low", "Informational"]
FindingStatus = Literal[
    "Open",
    "In Remediation",
    "Ready for Retest",
    "Fixed",
    "Accepted Risk",
    "Closed",
]
RetestStatus = Literal["Still Vulnerable", "Partially Fixed", "Fixed", "Unable to Retest"]
EvidenceType = Literal[
    "HTTP Request/Response",
    "Replay",
    "Response Comparison",
    "Operator Note",
    "Text Excerpt",
]


class NoteCreate(BaseModel):
    target_type: Literal["candidate", "finding", "evidence", "retest"]
    target_id: str
    body: str = Field(min_length=1, max_length=20_000)


class NoteResponse(BaseModel):
    id: str
    author_label: str
    body: str
    created_at: datetime


class EvidenceCreate(BaseModel):
    evidence_type: EvidenceType
    title: str = Field(min_length=1, max_length=200)
    source_exchange_id: str | None = None
    source_comparison_id: str | None = None
    source_candidate_id: str | None = None
    finding_id: str | None = None
    text: str | None = Field(default=None, max_length=100_000)

    @model_validator(mode="after")
    def source_matches_type(self) -> "EvidenceCreate":
        if self.evidence_type in {"HTTP Request/Response", "Replay"}:
            if self.source_exchange_id is None:
                raise ValueError("source_exchange_id is required for HTTP or replay evidence")
        elif self.evidence_type == "Response Comparison":
            if self.source_comparison_id is None:
                raise ValueError("source_comparison_id is required for comparison evidence")
        elif not self.text or not self.text.strip():
            raise ValueError("text is required for operator note or text excerpt evidence")
        return self


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    engagement_id: str
    display_id: str
    evidence_type: str
    title: str
    source_exchange_id: str | None
    source_comparison_id: str | None
    source_candidate_id: str | None
    finding_id: str | None
    author_label: str
    captured_at: datetime


class EvidenceResponse(EvidenceSummary):
    snapshot: dict[str, object]
    notes: list[NoteResponse] = []


class FindingPromotion(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    severity: Severity = "Medium"
    affected_asset: str = Field(default="", max_length=500)
    affected_endpoints: list[str] = Field(default_factory=list, max_length=100)
    description: str = Field(default="", max_length=100_000)
    impact: str = Field(default="", max_length=100_000)
    reproduction_steps: list[str] = Field(default_factory=list, max_length=100)
    remediation: str = Field(default="", max_length=100_000)
    references: list[str] = Field(default_factory=list, max_length=100)


class FindingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    severity: Severity | None = None
    status: FindingStatus | None = None
    affected_asset: str | None = Field(default=None, max_length=500)
    affected_endpoints: list[str] | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=100_000)
    impact: str | None = Field(default=None, max_length=100_000)
    reproduction_steps: list[str] | None = Field(default=None, max_length=100)
    remediation: str | None = Field(default=None, max_length=100_000)
    references: list[str] | None = Field(default=None, max_length=100)


class RetestCreate(BaseModel):
    status: RetestStatus
    tested_at: datetime | None = None
    operator_notes: str = Field(default="", max_length=20_000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class RetestUpdate(BaseModel):
    status: RetestStatus | None = None
    tested_at: datetime | None = None
    operator_notes: str | None = Field(default=None, max_length=20_000)
    evidence_ids: list[str] | None = Field(default=None, max_length=100)


class RetestResponse(BaseModel):
    id: str
    engagement_id: str
    finding_id: str
    finding_display_id: str
    display_id: str
    status: str
    tested_at: datetime
    operator_notes: str
    evidence_ids: list[str]
    created_at: datetime
    updated_at: datetime
    notes: list[NoteResponse] = []


class HistoryResponse(BaseModel):
    id: str
    event_type: str
    summary: str
    details: dict[str, object]
    created_at: datetime


class LatestRetestResponse(BaseModel):
    display_id: str
    status: str
    tested_at: datetime


class RelatedAttackChainResponse(BaseModel):
    id: str
    display_id: str
    title: str
    status: str


class FindingResponse(BaseModel):
    id: str
    engagement_id: str
    display_id: str
    candidate_id: str | None
    title: str
    category: str
    severity: str
    status: str
    affected_asset: str
    affected_endpoints: list[str]
    description: str
    impact: str
    reproduction_steps: list[str]
    remediation: str
    references: list[str]
    supporting_original_exchange_id: str | None
    supporting_comparison_id: str | None
    confirmed_at: datetime
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    latest_retest: LatestRetestResponse | None
    evidence_ids: list[str] = []
    notes: list[NoteResponse] = []
    retests: list[RetestResponse] = []
    history: list[HistoryResponse] = []
    attack_chains: list[RelatedAttackChainResponse] = []
