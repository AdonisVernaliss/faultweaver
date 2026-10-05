import json
import os
import secrets
from pathlib import Path

import pytest

from faultweaver.storage.database import check_integrity, open_database
from faultweaver.storage.keys import (
    FileKeyProvider,
    KeyMaterial,
    MemoryKeyProvider,
    NativeKeyProvider,
    StorageError,
    generate_key_file,
)


def marker() -> str:
    return "FW_TEST_STORAGE_" + secrets.token_hex(16)


def populate(path: Path, key: KeyMaterial, value: str) -> None:
    connection = open_database(path, key)
    try:
        connection.execute("CREATE TABLE protected_data (value TEXT)")
        connection.execute("INSERT INTO protected_data VALUES (?)", (value,))
        connection.commit()
        check_integrity(connection)
    finally:
        connection.close()


def test_encrypted_database_round_trip_randomization_and_key_separation(tmp_path: Path):
    key = KeyMaterial.generate()
    value = marker()
    first, second = tmp_path / "first.db", tmp_path / "second.db"
    populate(first, key, value)
    populate(second, key, value)
    assert first.read_bytes() != second.read_bytes()
    for path in (first, second):
        raw = path.read_bytes()
        forbidden = (
            value.encode(),
            key.secret,
            key.secret.hex().encode(),
            key.serialize().encode(),
        )
        assert not any(item in raw for item in forbidden)
        connection = open_database(path, key, readonly=True)
        try:
            assert connection.execute("SELECT value FROM protected_data").fetchone()[0] == value
        finally:
            connection.close()


def test_wrong_and_missing_key_leave_database_unchanged(tmp_path: Path):
    key = KeyMaterial.generate()
    path = tmp_path / "protected.db"
    value = marker()
    populate(path, key, value)
    before = path.read_bytes()
    for wrong in (None, KeyMaterial.generate()):
        with pytest.raises(StorageError):
            open_database(path, wrong)
        assert path.read_bytes() == before
    connection = open_database(path, key)
    assert connection.execute("SELECT value FROM protected_data").fetchone()[0] == value
    connection.close()


@pytest.mark.parametrize("offset", [100, 4096 - 70, 4096 - 10])
def test_ciphertext_iv_and_tag_tampering_are_rejected(tmp_path: Path, offset: int):
    key = KeyMaterial.generate()
    path = tmp_path / "tampered.db"
    populate(path, key, marker())
    raw = bytearray(path.read_bytes())
    raw[offset] ^= 1
    path.write_bytes(raw)
    with pytest.raises(StorageError, match="key|authentication"):
        connection = open_database(path, key)
        try:
            check_integrity(connection)
        finally:
            connection.close()
    assert path.read_bytes() == raw


def test_page_context_substitution_is_rejected(tmp_path: Path):
    key = KeyMaterial.generate()
    path = tmp_path / "pages.db"
    populate(path, key, marker() * 1000)
    raw = bytearray(path.read_bytes())
    assert len(raw) > 3 * 4096
    raw[8192:12288] = raw[4096:8192]
    path.write_bytes(raw)
    connection = open_database(path, key)
    try:
        with pytest.raises(StorageError, match="authentication"):
            check_integrity(connection)
    finally:
        connection.close()


def test_plaintext_is_not_silently_accepted(tmp_path: Path):
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE legacy (id INTEGER)")
    before = path.read_bytes()
    with pytest.raises(StorageError, match="migration"):
        open_database(path, KeyMaterial.generate())
    assert path.read_bytes() == before


def test_key_file_generation_permissions_separation_and_no_overwrite(tmp_path: Path):
    database = tmp_path / "data" / "workspace.db"
    path = tmp_path / "keys" / "master.key"
    generated = generate_key_file(path, database=database)
    provider = FileKeyProvider(path, database=database)
    assert provider.load().secret == generated.secret
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(StorageError, match="exists"):
        generate_key_file(path, database=database)
    with pytest.raises(StorageError, match="separate"):
        generate_key_file(database.parent / "master.key", database=database)
    if os.name == "posix":
        path.chmod(0o644)
        with pytest.raises(StorageError, match="permissions"):
            provider.load()


def test_key_file_rejects_symlinks_and_unsupported_version(tmp_path: Path):
    database = tmp_path / "data" / "workspace.db"
    path = tmp_path / "master.key"
    generate_key_file(path, database=database)
    alias = tmp_path / "alias.key"
    alias.symlink_to(path)
    with pytest.raises(StorageError):
        FileKeyProvider(alias, database=database).load()
    content = json.loads(path.read_text())
    content["version"] = 999
    path.write_text(json.dumps(content))
    with pytest.raises(StorageError, match="version"):
        FileKeyProvider(path, database=database).load()


def test_native_provider_never_creates_or_replaces_key_implicitly():
    class Backend:
        value = None

        def get_password(self, service, account):
            return self.value

        def set_password(self, service, account, value):
            self.value = value

    backend = Backend()
    provider = NativeKeyProvider(backend=backend)
    with pytest.raises(StorageError, match="initialize"):
        provider.load()
    assert backend.value is None
    initialized = provider.initialize()
    assert provider.load().secret == initialized.secret
    with pytest.raises(StorageError, match="already"):
        provider.initialize()
    assert provider.load().secret == initialized.secret
    assert MemoryKeyProvider(initialized).load() is initialized
    assert initialized.secret.hex() not in repr(initialized)


def test_key_failures_do_not_reveal_provider_content():
    secret = marker()

    class BrokenBackend:
        def get_password(self, service, account):
            raise RuntimeError(secret)

    with pytest.raises(StorageError) as caught:
        NativeKeyProvider(backend=BrokenBackend()).load()
    assert secret not in str(caught.value)
