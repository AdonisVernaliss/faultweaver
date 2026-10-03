from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from faultweaver.engagements.models import Engagement
from faultweaver.migrations.runner import upgrade_database


def test_migrations_create_a_fresh_database(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'fresh.db'}"

    upgrade_database(database_url)

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "attack_chain_evidence",
        "attack_chain_history",
        "attack_chain_step_evidence",
        "attack_chain_steps",
        "attack_chains",
        "candidate_replays",
        "candidates",
        "engagements",
        "engagement_sequences",
        "evidence",
        "finding_lifecycle_events",
        "findings",
        "http_exchanges",
        "identities",
        "operator_notes",
        "response_comparisons",
        "retest_evidence",
        "retests",
        "scope_rules",
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"


def test_baseline_adopts_the_existing_schema_without_losing_data(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(database_url)
    upgrade_database(database_url, "0001")
    with Session(engine) as session:
        session.add(Engagement(id="legacy-engagement", name="Preserved engagement"))
        session.commit()
        session.execute(text("DROP TABLE alembic_version"))
        session.commit()

    upgrade_database(database_url)

    with Session(engine) as session:
        preserved = session.get(Engagement, "legacy-engagement")
        assert preserved is not None
        assert preserved.name == "Preserved engagement"
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
        anonymous_count = session.scalar(
            text(
                "SELECT count(*) FROM identities "
                "WHERE engagement_id = 'legacy-engagement' AND is_anonymous = 1"
            )
        )
        assert anonymous_count == 1
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM engagement_sequences "
                    "WHERE engagement_id = 'legacy-engagement'"
                )
            )
            == 1
        )


def test_0002_upgrades_to_latest_without_losing_data(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'version-two.db'}"
    engine = create_engine(database_url)
    upgrade_database(database_url, "0002")
    with Session(engine) as session:
        session.add(Engagement(id="v2-engagement", name="Version two engagement"))
        session.commit()

    upgrade_database(database_url)

    with Session(engine) as session:
        assert session.get(Engagement, "v2-engagement") is not None
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
        assert (
            session.scalar(
                text(
                    "SELECT next_finding FROM engagement_sequences "
                    "WHERE engagement_id = 'v2-engagement'"
                )
            )
            == 1
        )


def test_0003_upgrades_to_latest_without_losing_sequence_data(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'version-three.db'}"
    engine = create_engine(database_url)
    upgrade_database(database_url, "0003")
    with Session(engine) as session:
        session.add(Engagement(id="v3-engagement", name="Version three engagement"))
        session.execute(
            text(
                "INSERT INTO engagement_sequences "
                "(engagement_id, next_finding, next_evidence, next_retest) "
                "VALUES ('v3-engagement', 7, 9, 3)"
            )
        )
        session.commit()

    upgrade_database(database_url)

    with Session(engine) as session:
        sequence = session.execute(
            text(
                "SELECT next_finding, next_evidence, next_retest, next_attack_chain "
                "FROM engagement_sequences WHERE engagement_id = 'v3-engagement'"
            )
        ).one()
        assert sequence == (7, 9, 3, 1)
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
