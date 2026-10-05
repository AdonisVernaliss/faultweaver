import os
from pathlib import Path
from urllib.parse import quote

from sqlcipher3 import dbapi2

from faultweaver.storage.keys import KeyMaterial, StorageError

SQLITE_HEADER = b"SQLite format 3\0"


def is_plaintext_database(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    with path.open("rb") as source:
        return source.read(16) == SQLITE_HEADER


def open_database(
    path: Path, key: KeyMaterial | None, *, readonly: bool = False
) -> dbapi2.Connection:
    """Open authenticated SQLCipher format 4; never retry with plaintext SQLite."""
    if key is None:
        raise StorageError("The existing encryption key is required")
    if is_plaintext_database(path):
        raise StorageError("Legacy plaintext database requires an explicit storage migration")
    if path.is_symlink():
        raise StorageError("Database path must not be a symbolic link")
    if not readonly:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
    connection = None
    try:
        uri = (
            "file:"
            + quote(str(path.absolute()), safe="/")
            + ("?mode=ro" if readonly else "?mode=rw")
        )
        connection = dbapi2.connect(uri, uri=True, check_same_thread=False, timeout=5)
        version = connection.execute("PRAGMA cipher_version").fetchone()
        if not version or not version[0].startswith("4."):
            raise StorageError("Unsupported SQLCipher version; format 4 support is required")
        # This is executed directly before any SQLAlchemy hooks or trace logging.
        # Only validated random bytes enter the raw-key literal, never user SQL.
        connection.execute(f'''PRAGMA key = "x'{key.secret.hex()}'"''')
        connection.execute("PRAGMA cipher_compatibility = 4")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA cipher_memory_security = ON")
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except StorageError:
        if connection is not None:
            connection.close()
        raise
    except (dbapi2.Error, OSError):
        if connection is not None:
            connection.close()
        raise StorageError(
            "Storage key or database authentication failed; data was not replaced"
        ) from None


def check_integrity(connection: dbapi2.Connection) -> None:
    try:
        if connection.execute("PRAGMA cipher_integrity_check").fetchall():
            raise StorageError("Database authentication failed")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise StorageError("Database integrity check failed")
    except dbapi2.Error:
        raise StorageError("Database authentication or integrity check failed") from None
