from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection

from faultweaver.database import ensure_sqlite_directory


def upgrade_database(
    database_url: str, revision: str = "head", *, connection: Connection | None = None
) -> None:
    """Schema-only upgrade. Runtime callers must supply an authenticated connection."""
    ensure_sqlite_directory(database_url)
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    if connection is not None:
        config.attributes["connection"] = connection
    command.upgrade(config, revision)
