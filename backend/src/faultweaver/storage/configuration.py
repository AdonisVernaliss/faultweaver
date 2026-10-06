from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from faultweaver.config import Settings
from faultweaver.storage.keys import (
    FileKeyProvider,
    NativeKeyProvider,
    SecretKeyProvider,
    StorageError,
)


def database_path(database_url: str) -> Path:
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        raise StorageError("Protected storage requires a local SQLite file URL") from None
    if (
        url.drivername != "sqlite"
        or not url.database
        or url.database == ":memory:"
        or url.query
        or url.host
        or url.username
        or url.password
        or url.port
    ):
        raise StorageError("Protected storage requires a local SQLite file URL")
    return Path(url.database).absolute()


def key_provider_for(settings: Settings) -> SecretKeyProvider:
    if settings.storage_key_provider == "file":
        if settings.master_key_file is None:
            raise StorageError("File provider requires FAULTWEAVER_MASTER_KEY_FILE")
        return FileKeyProvider(settings.master_key_file, database_path(settings.database_url))
    if settings.storage_key_provider == "native":
        if settings.master_key_file is not None:
            raise StorageError("Explicitly select the file key provider to use a mounted key")
        return NativeKeyProvider(settings.keyring_account)
    raise StorageError("Unknown storage key provider; select native or file explicitly")
