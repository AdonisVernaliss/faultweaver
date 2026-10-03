from datetime import datetime

from pydantic import BaseModel, Field


class ImportDocument(BaseModel):
    content: str = Field(min_length=1)
    filename: str | None = Field(default=None, max_length=1_000)


class ImportRequestPreview(BaseModel):
    source_entry_index: int | None
    method: str
    url: str
    header_count: int
    cookie_count: int
    body_kind: str | None
    body_bytes: int
    response_status: int | None
    scope_allowed: bool


class ImportEndpointPreview(BaseModel):
    method: str
    path_template: str
    server_url: str | None
    operation_id: str | None
    auth: list[str]


class ImportPreviewResponse(BaseModel):
    import_format: str
    total_records: int
    accepted_count: int
    response_count: int
    skipped_count: int
    warnings: list[str]
    requests: list[ImportRequestPreview]
    endpoints: list[ImportEndpointPreview]


class ImportBatchResponse(BaseModel):
    id: str
    engagement_id: str
    display_id: str
    import_format: str
    original_filename: str | None
    status: str
    total_records: int
    imported_count: int
    response_count: int
    skipped_count: int
    warning_count: int
    new_endpoint_count: int
    known_endpoint_count: int
    warnings: list[str]
    created_at: datetime


class ImportResultResponse(BaseModel):
    batch: ImportBatchResponse
    request_ids: list[str]
    endpoint_ids: list[str]


class AttackSurfaceEndpointResponse(BaseModel):
    id: str
    method: str
    scheme: str | None
    host: str | None
    port: int | None
    path_template: str
    sources: list[str]
    observed_request_count: int
    declared_by_openapi: bool
    state: str
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
