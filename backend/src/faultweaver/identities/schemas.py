from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from faultweaver.http_traffic.schemas import HeaderEntry


class CookieEntry(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    value: str = Field(max_length=16_384)


class IdentityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10_000)
    bearer_token: str | None = Field(default=None, max_length=65_536)
    api_key_header: str | None = Field(default=None, min_length=1, max_length=160)
    api_key_value: str | None = Field(default=None, max_length=65_536)
    cookies: list[CookieEntry] = Field(default_factory=list, max_length=100)
    custom_headers: list[HeaderEntry] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_api_key_pair(self) -> "IdentityCreate":
        if (self.api_key_header is None) != (self.api_key_value is None):
            raise ValueError("api_key_header and api_key_value must be provided together")
        return self


class IdentityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    bearer_token: str | None = Field(default=None, max_length=65_536)
    api_key_header: str | None = Field(default=None, min_length=1, max_length=160)
    api_key_value: str | None = Field(default=None, max_length=65_536)
    cookies: list[CookieEntry] | None = Field(default=None, max_length=100)
    custom_headers: list[HeaderEntry] | None = Field(default=None, max_length=100)


class IdentityResponse(BaseModel):
    id: str
    engagement_id: str
    name: str
    description: str
    is_anonymous: bool
    bearer_token: str | None
    api_key_header: str | None
    api_key_value: str | None
    cookies: list[CookieEntry]
    custom_headers: list[HeaderEntry]
    created_at: datetime
    updated_at: datetime
