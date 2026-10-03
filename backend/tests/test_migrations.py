from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from faultweaver.database import Base
from faultweaver.engagements.models import Engagement
from faultweaver.migrations.runner import upgrade_database


def test_migrations_create_a_fresh_database(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'fresh.db'}"

    upgrade_database(database_url)

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "engagements",
        "http_exchanges",
        "scope_rules",
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"


def test_baseline_adopts_the_existing_schema_without_losing_data(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Engagement(id="legacy-engagement", name="Preserved engagement"))
        session.commit()

    upgrade_database(database_url)

    with Session(engine) as session:
        preserved = session.get(Engagement, "legacy-engagement")
        assert preserved is not None
        assert preserved.name == "Preserved engagement"
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
