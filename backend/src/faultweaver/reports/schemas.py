from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from faultweaver.findings.schemas import FindingStatus, RetestStatus, Severity


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ReportContent(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    executive_summary: str = Field(default="", max_length=30_000)
    methodology: str = Field(default="", max_length=30_000)
    limitations: str = Field(default="", max_length=30_000)
    conclusion: str = Field(default="", max_length=30_000)
    finding_ids: list[str] | None = Field(default=None, max_length=1000)
    attack_chain_ids: list[str] | None = Field(default=None, max_length=200)
    include_informational: bool = True
    include_archived: bool = False
    include_draft_chains: bool = False
    include_retest_history: bool = True

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Report title must not be blank")
        return value.strip()


class ReportUpdate(ReportContent):
    title: str = Field(default="Report", min_length=1, max_length=200)
    version: int = Field(ge=1)
    status: Literal["Draft", "Ready", "Archived"] | None = None


class GenerateRequest(StrictModel):
    version: int = Field(ge=1)


class ReportSummary(StrictModel):
    id: str
    engagement_id: str
    display_id: str
    title: str
    status: Literal["Draft", "Ready", "Generated", "Archived"]
    version: int
    revision_count: int
    created_at: datetime
    updated_at: datetime
    generated_at: datetime | None


class ReportResponse(ReportSummary, ReportContent):
    pass


class RevisionSummary(StrictModel):
    revision: int
    generated_at: datetime
    schema_version: str
    document_sha256: str


class DocumentReport(StrictModel):
    id: str
    display_id: str
    title: str
    revision: int | None
    generated_at: datetime | None
    executive_summary: str
    methodology: str
    limitations: str
    conclusion: str


class DocumentEngagement(StrictModel):
    id: str
    name: str
    description: str
    status: str
    created_at: datetime


class DocumentScope(StrictModel):
    scheme: str
    host: str
    port: int
    path_prefix: str
    active: bool


class DocumentSummary(StrictModel):
    finding_count: int
    severity: dict[Severity, int]
    attack_chain_count: int
    retested_findings: int
    latest_retest_results: dict[RetestStatus, int]


class DocumentFinding(StrictModel):
    display_id: str
    title: str
    severity: Severity
    status: FindingStatus
    archived: bool
    affected_asset: str
    affected_endpoints: list[str]
    description: str
    impact: str
    reproduction_steps: list[str]
    remediation: str
    references: list[str]
    confirmed_at: datetime
    finding_evidence_ids: list[str]
    latest_retest: RetestStatus | Literal["Not Retested"]


class EvidenceExcerpt(StrictModel):
    label: str
    text: str
    truncated: bool


class DocumentEvidence(StrictModel):
    display_id: str
    title: str
    evidence_type: str
    captured_at: datetime
    excerpts: list[EvidenceExcerpt]


class DocumentRetest(StrictModel):
    display_id: str
    finding_id: str
    status: RetestStatus
    tested_at: datetime
    operator_notes: str
    evidence_ids: list[str]
    latest: bool


class DocumentStep(StrictModel):
    position: int
    kind: Literal["Finding", "Intermediate"]
    finding_id: str | None
    title: str
    description: str
    evidence_ids: list[str]


class DocumentChain(StrictModel):
    display_id: str
    title: str
    status: Literal["Draft", "Validated", "Archived"]
    description: str
    resulting_impact: str
    steps: list[DocumentStep]
    evidence_ids: list[str]


class DocumentAssessment(StrictModel):
    display_id: str
    target_url: str
    status: str
    request_count: int
    started_at: datetime | None
    finished_at: datetime | None


class ReportDocument(StrictModel):
    report_schema_version: Literal["1.0"] = "1.0"
    application_version: str
    renderer_version: Literal["1"] = "1"
    report: DocumentReport
    engagement: DocumentEngagement
    scope: list[DocumentScope]
    summary: DocumentSummary
    findings: list[DocumentFinding]
    evidence: list[DocumentEvidence]
    attack_chains: list[DocumentChain]
    retests: list[DocumentRetest]
    assessments: list[DocumentAssessment]
    warnings: list[str]
