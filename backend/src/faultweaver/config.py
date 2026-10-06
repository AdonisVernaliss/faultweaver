from dataclasses import dataclass
from os import environ
from pathlib import Path
from urllib.parse import urlsplit

from faultweaver.storage.keys import StorageError


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    allowed_origins: tuple[str, ...]
    request_timeout_seconds: float = 10.0
    max_response_bytes: int = 1_000_000
    max_redirects: int = 5
    max_import_bytes: int = 10_000_000
    max_import_entries: int = 5_000
    max_import_request_body_bytes: int = 1_000_000
    max_import_response_body_bytes: int = 1_000_000
    storage_key_provider: str = "native"
    master_key_file: Path | None = None
    keyring_account: str = "local-storage-v1"

    @classmethod
    def from_environment(cls) -> "Settings":
        default_database = Path("data/faultweaver.db").absolute()
        origins = environ.get("FAULTWEAVER_ALLOWED_ORIGINS", "http://localhost:5173")
        allowed_origins = tuple(origin.strip() for origin in origins.split(",") if origin.strip())
        for origin in allowed_origins:
            try:
                parsed = urlsplit(origin)
                valid = (
                    parsed.scheme in {"http", "https"}
                    and parsed.hostname
                    and not parsed.username
                    and not parsed.password
                    and not parsed.path
                    and not parsed.query
                    and not parsed.fragment
                )
                _ = parsed.port
            except ValueError:
                valid = False
            if not valid:
                raise StorageError(
                    "Origins must be explicit HTTP or HTTPS origins without paths or credentials"
                )
        account = environ.get("FAULTWEAVER_KEYRING_ACCOUNT", "local-storage-v1")
        if not account.strip():
            raise StorageError("The native key-store account must not be blank")
        return cls(
            database_url=environ.get("FAULTWEAVER_DATABASE_URL", f"sqlite:///{default_database}"),
            allowed_origins=allowed_origins,
            storage_key_provider=environ.get("FAULTWEAVER_KEY_PROVIDER", "native"),
            master_key_file=(
                Path(environ["FAULTWEAVER_MASTER_KEY_FILE"])
                if environ.get("FAULTWEAVER_MASTER_KEY_FILE")
                else None
            ),
            keyring_account=account,
        )
