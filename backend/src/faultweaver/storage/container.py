"""Read a private Docker secret, then permanently drop API process privileges."""

import argparse
import os
import sys
from pathlib import Path

from faultweaver.config import Settings
from faultweaver.storage.configuration import database_path, key_provider_for
from faultweaver.storage.keys import MemoryKeyProvider, StorageError
from faultweaver.storage.migration import migrate_plaintext


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Protected container startup")
    parser.add_argument("command", nargs="?", choices=("serve", "migrate"), default="serve")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_environment()
        if settings.storage_key_provider != "file":
            raise StorageError("Container startup requires an explicitly mounted private key file")
        key = key_provider_for(settings).load()
        if args.command == "migrate":
            if args.backup is None:
                raise StorageError("Offline migration requires a separate private backup")
            path = database_path(settings.database_url)
            counts = migrate_plaintext(path, key, args.backup)
            if os.geteuid() == 0:
                import pwd

                account = pwd.getpwnam("nobody")
                os.chown(path, account.pw_uid, account.pw_gid)
                os.chown(str(path) + ".lock", account.pw_uid, account.pw_gid)
            print(f"Protected storage verified; {sum(counts.values())} legacy rows converted.")
            return 0
        if os.geteuid() == 0:
            import pwd

            account = pwd.getpwnam("nobody")
            os.setgroups([])
            os.setgid(account.pw_gid)
            os.setuid(account.pw_uid)
        if os.geteuid() == 0:
            raise StorageError("Refusing to run the API with root privileges")
        import uvicorn

        from faultweaver.app import create_app

        uvicorn.run(
            create_app(settings, key_provider=MemoryKeyProvider(key)),
            host="0.0.0.0",
            port=8000,
            access_log=False,
        )
        return 0
    except StorageError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, KeyError):
        print(
            "Protected container startup failed; check mounted key and data permissions",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
