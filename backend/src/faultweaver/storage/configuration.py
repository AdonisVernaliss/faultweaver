from pathlib import Path

from sqlalchemy.engine import make_url

from faultweaver.config import Settings
from faultweaver.storage.keys import (
    FileKeyProvider,
    NativeKeyProvider,
    SecretKeyProvider,
    StorageError,
)


def database_path(database_url: str) -> Path:
    url = make_url(database_url)
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:" or url.query:
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
