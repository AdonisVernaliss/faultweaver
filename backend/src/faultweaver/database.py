from collections.abc import Generator
from pathlib import Path
from typing import NoReturn

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlcipher3 import dbapi2

from faultweaver.storage.configuration import database_path
from faultweaver.storage.database import open_database
from faultweaver.storage.keys import KeyMaterial


class Base(DeclarativeBase):
    pass


def ensure_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix) and database_url != "sqlite:///:memory:":
        Path(database_url.removeprefix(prefix)).parent.mkdir(parents=True, exist_ok=True)


def create_storage_engine(database_url: str, key: KeyMaterial) -> Engine:
    path = database_path(database_url)
    return create_engine(
        database_url,
        module=dbapi2,
        creator=lambda: open_database(path, key),
        hide_parameters=True,
    )


def session_dependency(factory: sessionmaker[Session]) -> Generator[Session]:
    with factory() as session:
        yield session


def get_session() -> NoReturn:
    raise RuntimeError("Database dependency was not configured")
