import argparse
import sys
from contextlib import closing
from pathlib import Path

from faultweaver.config import Settings
from faultweaver.storage.configuration import database_path, key_provider_for
from faultweaver.storage.database import check_integrity, open_database
from faultweaver.storage.keys import (
    FileKeyProvider,
    NativeKeyProvider,
    StorageError,
    generate_key_file,
)
from faultweaver.storage.locking import storage_lock
from faultweaver.storage.migration import migrate_plaintext


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Faultweaver protected-storage administration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "init-key", help="Explicitly create a new key; never replaces an existing key"
    )
    migration = commands.add_parser("migrate", help="Offline plaintext-to-encrypted conversion")
    migration.add_argument("--backup", required=True, type=Path)
    commands.add_parser("check", help="Authenticate all database pages without modifying data")
    backup_key = commands.add_parser(
        "backup-key", help="Explicitly export the existing key to a private file"
    )
    backup_key.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_environment()
        database = database_path(settings.database_url)
        provider = key_provider_for(settings)
        if args.command == "init-key":
            if database.exists() and database.stat().st_size and not _legacy(database):
                raise StorageError(
                    "Existing protected database: restore its key, do not initialize"
                )
            if isinstance(provider, FileKeyProvider):
                generate_key_file(provider.path, database=database)
            elif isinstance(provider, NativeKeyProvider):
                provider.initialize()
            else:
                raise StorageError("Provider does not support persistent key initialization")
            print("Storage key initialized. Back it up separately from the database.")
        elif args.command == "backup-key":
            generate_key_file(args.output, database=database, material=provider.load())
            print("Private key backup created. Store it independently of database backups.")
        elif args.command == "migrate":
            counts = migrate_plaintext(database, provider.load(), args.backup)
            print(f"Protected storage verified; {sum(counts.values())} legacy rows converted.")
        else:
            with (
                storage_lock(database),
                closing(open_database(database, provider.load(), readonly=True)) as db,
            ):
                check_integrity(db)
            print("Protected storage authentication and integrity checks passed.")
        return 0
    except StorageError as error:
        print(str(error), file=sys.stderr)
        return 1


def _legacy(path: Path) -> bool:
    from faultweaver.storage.database import is_plaintext_database

    return is_plaintext_database(path)


if __name__ == "__main__":
    raise SystemExit(main())
