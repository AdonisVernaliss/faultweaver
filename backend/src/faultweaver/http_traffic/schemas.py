from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class HeaderEntry(BaseModel):
    name: str
    value: str


class RawImportCreate(BaseModel):
    base_url: AnyHttpUrl
    raw: str = Field(min_length=1, max_length=2_000_000)


class ReplayCreate(BaseModel):
    method: str | None = Field(default=None, min_length=1, max_length=16)
    url: AnyHttpUrl | None = None
    headers: list[HeaderEntry] | None = None
    body: str | None = Field(default=None, max_length=2_000_000)

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class ExchangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    engagement_id: str
    parent_exchange_id: str | None
    source: str
    method: str
    url: str
    host: str
    path: str
    query: str
    request_headers: list[HeaderEntry]
    request_body: str | None
    response_status: int | None
    response_headers: list[HeaderEntry]
    response_body: str | None
    response_elapsed_ms: float | None
    response_truncated: bool
    redirect_chain: list[str]
    created_at: datetime


class ExchangeDetail(ExchangeResponse):
    raw_request: str


class ExchangeList(BaseModel):
    items: list[ExchangeResponse]
    total: int
