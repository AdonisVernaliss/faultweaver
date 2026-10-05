"""Explicit offline conversion. Ordinary application code never opens plaintext."""

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from sqlcipher3 import dbapi2

from faultweaver.storage.database import check_integrity, is_plaintext_database, open_database
from faultweaver.storage.keys import KeyMaterial, StorageError, ensure_key_location
from faultweaver.storage.locking import storage_lock, sync_directory


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def logical_fingerprint(connection: dbapi2.Connection) -> tuple[str, dict[str, int]]:
    """Streaming exact schema/typed row digest; never log rows or secret values."""
    digest = hashlib.sha256()
    schema = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_stat%' ORDER BY type, name"
    ).fetchall()
    digest.update(json.dumps(schema, ensure_ascii=True).encode())
    counts = {}
    for kind, name, _, _ in schema:
        if kind != "table":
            continue
        table = _identifier(name)
        columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
        ordering = ", ".join(_identifier(column[1]) for column in columns)
        count = 0
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY {ordering}"):
            values = [
                ["blob", value.hex()] if isinstance(value, bytes) else [type(value).__name__, value]
                for value in row
            ]
            digest.update(json.dumps(values, ensure_ascii=True).encode() + b"\n")
            count += 1
        counts[name] = count
    return digest.hexdigest(), counts


def _backup(source: Path, destination: Path) -> None:
    ensure_key_location(destination, source)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise StorageError("Backup destination already exists; choose a new private backup path")
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as output, source.open("rb") as original:
        shutil.copyfileobj(original, output)
        output.flush()
        os.fsync(output.fileno())
    sync_directory(destination.parent)


def migrate_plaintext(database: Path, key: KeyMaterial, backup: Path) -> dict[str, int]:
    """Verify before atomic replacement; failures leave source and backup recoverable."""
    ensure_key_location(backup, database)
    if database.is_symlink() or not database.is_file():
        raise StorageError("Migration requires an existing regular database file")
    with storage_lock(database):
        if not is_plaintext_database(database):
            with closing(open_database(database, key, readonly=True)) as existing:
                check_integrity(existing)
            return {}  # Already protected; do not create another plaintext backup.
        temporary = None
        source = None
        try:
            uri = "file:" + quote(str(database.absolute()), safe="/") + "?mode=rw"
            source = dbapi2.connect(uri, uri=True, timeout=0, isolation_level=None)
            source.execute("PRAGMA temp_store = MEMORY")
            source.execute("PRAGMA locking_mode = EXCLUSIVE")
            result = source.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if result and result[0] != 0:
                raise StorageError("Legacy database is busy; stop all database users")
            source.execute("PRAGMA journal_mode = DELETE")
            source.execute("BEGIN EXCLUSIVE")
            if source.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise StorageError("Legacy database integrity check failed")
            before = logical_fingerprint(source)
            _backup(database, backup)
            descriptor, filename = tempfile.mkstemp(
                prefix=".storage-conversion-", dir=database.parent
            )
            os.close(descriptor)
            temporary = Path(filename)
            # SQLCipher owns the encryption format. Never print/trace this DBAPI statement.
            source.execute(
                f'''ATTACH DATABASE ? AS protected KEY "x'{key.secret.hex()}'"''',
                (str(temporary),),
            )
            source.execute("PRAGMA protected.cipher_compatibility = 4")
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute("COMMIT")
            source.execute("DETACH DATABASE protected")
            with closing(open_database(temporary, key, readonly=True)) as protected:
                check_integrity(protected)
                if logical_fingerprint(protected) != before:
                    raise StorageError("Migration verification failed; original database retained")
            source.close()
            source = None
            if any(
                Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")
            ):
                raise StorageError("Legacy sidecars remain; stop database users and retry safely")
            with temporary.open("rb") as output:
                os.fsync(output.fileno())
            os.replace(temporary, database)
            temporary = None
            sync_directory(database.parent)
            return before[1]
        except StorageError:
            raise
        except (OSError, dbapi2.Error):
            raise StorageError(
                "Storage migration failed; retain the original and private backup for recovery"
            ) from None
        finally:
            if source is not None:
                source.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
                for suffix in ("-wal", "-shm", "-journal"):
                    Path(str(temporary) + suffix).unlink(missing_ok=True)
