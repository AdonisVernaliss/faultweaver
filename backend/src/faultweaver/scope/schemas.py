from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from faultweaver.scope.rules import (
    default_port,
    normalize_hostname,
    normalize_path_prefix,
    normalize_scheme,
)


class ScopeCreate(BaseModel):
    scheme: Literal["http", "https"] | str
    hostname: str = Field(min_length=1, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    path_prefix: str = Field(default="/", max_length=2048)

    @field_validator("scheme")
    @classmethod
    def validate_scheme(cls, value: str) -> str:
        return normalize_scheme(value)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        return normalize_hostname(value)

    @field_validator("path_prefix")
    @classmethod
    def validate_path_prefix(cls, value: str) -> str:
        return normalize_path_prefix(value)

    def resolved_port(self) -> int:
        return self.port or default_port(self.scheme)


class ScopeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    engagement_id: str
    scheme: str
    hostname: str
    port: int
    path_prefix: str
    active: bool
