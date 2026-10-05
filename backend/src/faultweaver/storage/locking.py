import os
from contextlib import contextmanager
from pathlib import Path

from faultweaver.storage.keys import StorageError


@contextmanager
def storage_lock(database: Path):
    """One application or offline operation per database, including schema upgrades."""
    database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(str(database) + ".lock", flags, 0o600)
        if os.name == "posix":
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            raise StorageError("Database locking is unavailable on this platform")
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        raise StorageError("Storage is busy or unavailable; stop other database users") from None
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)


def sync_directory(directory: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
