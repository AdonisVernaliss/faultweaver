from __future__ import annotations

import base64
import json
import os
import secrets
import stat
import sys
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Protocol


class StorageError(RuntimeError):
    """An operational storage error whose message contains no protected material."""


@dataclass(frozen=True, slots=True)
class KeyMaterial:
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.secret, bytes) or len(self.secret) != 32:
            raise StorageError("Storage keys must contain exactly 32 random bytes")

    @classmethod
    def generate(cls) -> KeyMaterial:
        return cls(secrets.token_bytes(32))

    @property
    def key_id(self) -> str:
        return sha256(b"Faultweaver storage key v1\0" + self.secret).hexdigest()[:32]

    def serialize(self) -> str:
        return json.dumps({"version": 1, "key": base64.b64encode(self.secret).decode("ascii")})

    @classmethod
    def parse(cls, value: str) -> KeyMaterial:
        try:
            record = json.loads(value)
            if (
                not isinstance(record, dict)
                or type(record.get("version")) is not int
                or record["version"] != 1
            ):
                raise StorageError("Unsupported storage key format version")
            if set(record) != {"version", "key"} or not isinstance(record["key"], str):
                raise ValueError
            return cls(base64.b64decode(record["key"], validate=True))
        except StorageError:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise StorageError("Invalid storage key file or key-store entry") from None


class SecretKeyProvider(Protocol):
    def load(self) -> KeyMaterial: ...


@dataclass(frozen=True, slots=True)
class MemoryKeyProvider:
    """Explicit process-local injection; never selected implicitly by configuration."""

    material: KeyMaterial = field(repr=False)

    def load(self) -> KeyMaterial:
        return self.material


def ensure_key_location(path: Path, database: Path) -> None:
    resolved = path.absolute().resolve()
    if resolved.is_relative_to(database.absolute().resolve().parent):
        raise StorageError("Keep the key separate from the database data directory")
    if any((parent / ".git").exists() for parent in resolved.parents):
        raise StorageError("Keep generated storage keys outside Git repositories")


@dataclass(frozen=True, slots=True)
class FileKeyProvider:
    path: Path
    database: Path

    def load(self) -> KeyMaterial:
        if os.name != "posix":
            raise StorageError(
                "Private file keys require POSIX permissions; use the native provider"
            )
        ensure_key_location(self.path, self.database)
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(self.path, flags)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024:
                raise StorageError("Invalid storage key file")
            if os.name == "posix":
                if metadata.st_mode & 0o077:
                    raise StorageError("Insecure key-file permissions; use owner-only access")
                if os.geteuid() != 0 and metadata.st_uid != os.geteuid():
                    raise StorageError("Storage key file must belong to the current operator")
            return KeyMaterial.parse(os.read(descriptor, 1025).decode("utf-8"))
        except StorageError:
            raise
        except (OSError, UnicodeError):
            raise StorageError(
                "Storage key file unavailable; supply the existing private key"
            ) from None
        finally:
            if descriptor is not None:
                os.close(descriptor)


def generate_key_file(
    path: Path, *, database: Path, material: KeyMaterial | None = None
) -> KeyMaterial:
    if os.name != "posix":
        raise StorageError("Private file keys require POSIX permissions; use the native provider")
    ensure_key_location(path, database)
    key = material or KeyMaterial.generate()
    descriptor = None
    created = False
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = None
            output.write(key.serialize() + "\n")
            output.flush()
            os.fsync(output.fileno())
        from faultweaver.storage.locking import sync_directory

        sync_directory(path.parent)
    except FileExistsError:
        raise StorageError("Storage key file already exists; it will not be replaced") from None
    except OSError:
        if created:
            path.unlink(missing_ok=True)
        raise StorageError("Could not create the private storage key file") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return key


class NativeKeyProvider:
    service = "Faultweaver"

    def __init__(self, account: str = "local-storage-v1", *, backend: object | None = None):
        self.account = account
        self._backend = backend

    def _store(self):
        if self._backend is not None:
            return self._backend
        # Select only an OS-backed implementation. Never use autodiscovery,
        # environment-configured alternate backends, or plaintext fallbacks.
        try:
            if sys.platform == "darwin":
                from keyring.backends.macOS import Keyring
            elif sys.platform == "linux":
                from keyring.backends.SecretService import Keyring
            elif sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring as Keyring
            else:
                raise StorageError("No supported native key store; configure a private key file")
            self._backend = Keyring()
            return self._backend
        except StorageError:
            raise
        except Exception:
            raise StorageError(
                "Native key store unavailable; unlock it or configure a private key file"
            ) from None

    def load(self) -> KeyMaterial:
        try:
            value = self._store().get_password(self.service, self.account)
        except Exception:
            raise StorageError(
                "Native key store unavailable; unlock it or configure a private key file"
            ) from None
        if value is None:
            raise StorageError(
                "Storage key missing; initialize it explicitly or restore the existing key"
            )
        return KeyMaterial.parse(value)

    def initialize(self) -> KeyMaterial:
        try:
            store = self._store()
            if store.get_password(self.service, self.account) is not None:
                raise StorageError(
                    "Native storage key is already initialized; it will not be replaced"
                )
            material = KeyMaterial.generate()
            store.set_password(self.service, self.account, material.serialize())
            if self.load().secret != material.secret:
                raise StorageError("Native key store verification failed")
            return material
        except StorageError:
            raise
        except Exception:
            raise StorageError("Could not initialize native secure storage") from None
