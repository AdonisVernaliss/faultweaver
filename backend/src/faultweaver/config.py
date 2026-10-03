from dataclasses import dataclass
from os import environ
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    allowed_origins: tuple[str, ...]
    request_timeout_seconds: float = 10.0
    max_response_bytes: int = 1_000_000
    max_redirects: int = 5

    @classmethod
    def from_environment(cls) -> "Settings":
        default_database = Path("data/faultweaver.db").absolute()
        origins = environ.get("FAULTWEAVER_ALLOWED_ORIGINS", "http://localhost:5173")
        return cls(
            database_url=environ.get("FAULTWEAVER_DATABASE_URL", f"sqlite:///{default_database}"),
            allowed_origins=tuple(
                origin.strip() for origin in origins.split(",") if origin.strip()
            ),
        )
