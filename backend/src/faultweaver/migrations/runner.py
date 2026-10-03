from pathlib import Path

from alembic import command
from alembic.config import Config

from faultweaver.database import ensure_sqlite_directory


def upgrade_database(database_url: str, revision: str = "head") -> None:
    """Upgrade a Faultweaver database using the packaged migration history."""
    ensure_sqlite_directory(database_url)
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, revision)
