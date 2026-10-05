import json
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
        "attack_surface_endpoints",
        "assessment_runs",
        "baseline_observations",
        "candidate_replays",
        "candidates",
        "crawl_discoveries",
        "crawl_forms",
        "engagements",
        "engagement_sequences",
        "evidence",
        "finding_lifecycle_events",
        "findings",
        "http_exchanges",
        "identities",
        "import_batches",
        "operator_notes",
        "response_comparisons",
        "retest_evidence",
        "retests",
        "scope_rules",
        "storage_metadata",
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0007"


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
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
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
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
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
                "SELECT next_finding, next_evidence, next_retest, next_attack_chain, next_import "
                "FROM engagement_sequences WHERE engagement_id = 'v3-engagement'"
            )
        ).one()
        assert sequence == (7, 9, 3, 1, 1)
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0007"


def test_0004_upgrades_to_latest_and_backfills_attack_surface(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'version-four.db'}"
    engine = create_engine(database_url)
    upgrade_database(database_url, "0004")
    with Session(engine) as session:
        session.add(Engagement(id="v4-engagement", name="Version four engagement"))
        session.execute(
            text(
                "INSERT INTO engagement_sequences "
                "(engagement_id, next_finding, next_evidence, next_retest, next_attack_chain) "
                "VALUES ('v4-engagement', 7, 9, 3, 4)"
            )
        )
        session.execute(
            text(
                "INSERT INTO http_exchanges "
                "(id, engagement_id, auth_source, operator_modified, source, method, url, host, "
                "path, query, request_headers, response_headers, response_truncated, "
                "redirect_chain, created_at) VALUES "
                "('request-one', 'v4-engagement', 'original', 0, 'raw_import', 'GET', "
                "'https://example.test/api/users/17', 'example.test', '/api/users/17', '', "
                "'[]', '[]', 0, '[]', CURRENT_TIMESTAMP)"
            )
        )
        session.commit()

    upgrade_database(database_url)

    with Session(engine) as session:
        sequence = session.execute(
            text(
                "SELECT next_finding, next_evidence, next_retest, next_attack_chain, next_import "
                "FROM engagement_sequences WHERE engagement_id = 'v4-engagement'"
            )
        ).one()
        endpoint = session.execute(
            text(
                "SELECT method, host, path_template FROM attack_surface_endpoints "
                "WHERE engagement_id = 'v4-engagement'"
            )
        ).one()
        endpoint_id = session.scalar(
            text("SELECT endpoint_id FROM http_exchanges WHERE id = 'request-one'")
        )
        assert sequence == (7, 9, 3, 4, 1)
        assert endpoint == ("GET", "example.test", "/api/users/17")
        assert endpoint_id is not None
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0007"


def test_0005_upgrades_to_latest_and_preserves_existing_candidates(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'version-five.db'}"
    engine = create_engine(database_url)
    upgrade_database(database_url, "0005")
    with Session(engine) as session:
        session.add(Engagement(id="v5-engagement", name="Version five engagement"))
        session.execute(
            text(
                "INSERT INTO engagement_sequences "
                "(engagement_id, next_finding, next_evidence, next_retest, "
                "next_attack_chain, next_import) "
                "VALUES ('v5-engagement', 2, 3, 4, 5, 6)"
            )
        )
        session.execute(
            text(
                "INSERT INTO identities "
                "(id, engagement_id, name, description, is_anonymous, cookies, custom_headers, "
                "created_at, updated_at) VALUES "
                "('identity-a', 'v5-engagement', 'Identity A', '', 0, '[]', '[]', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "('identity-b', 'v5-engagement', 'Identity B', '', 0, '[]', '[]', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        for exchange_id in ("original-request", "replay-a", "replay-b"):
            session.execute(
                text(
                    "INSERT INTO http_exchanges "
                    "(id, engagement_id, auth_source, operator_modified, source, method, url, "
                    "host, path, query, request_headers, response_headers, response_truncated, "
                    "redirect_chain, created_at) VALUES "
                    "(:id, 'v5-engagement', 'original', 0, 'manual', 'GET', "
                    "'https://example.test/account', 'example.test', '/account', '', '[]', "
                    "'[]', 0, '[]', CURRENT_TIMESTAMP)"
                ),
                {"id": exchange_id},
            )
        session.execute(
            text(
                "INSERT INTO response_comparisons "
                "(id, engagement_id, original_exchange_id, replay_a_id, replay_b_id, "
                "identity_a_id, identity_b_id, result, created_at) VALUES "
                "('comparison-one', 'v5-engagement', 'original-request', 'replay-a', "
                "'replay-b', 'identity-a', 'identity-b', '{}', CURRENT_TIMESTAMP)"
            )
        )
        session.execute(
            text(
                "INSERT INTO candidates "
                "(id, engagement_id, comparison_id, original_exchange_id, title, category, "
                "confidence, status, reasoning, notes, created_at, updated_at) VALUES "
                "('candidate-one', 'v5-engagement', 'comparison-one', 'original-request', "
                "'Preserved candidate', 'authorization', 'Medium', 'Pending', '[]', '', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        session.execute(
            text(
                "INSERT INTO candidate_replays (candidate_id, exchange_id) VALUES "
                "('candidate-one', 'replay-a'), ('candidate-one', 'replay-b')"
            )
        )
        session.commit()

    upgrade_database(database_url)

    with Session(engine) as session:
        sequence = session.execute(
            text(
                "SELECT next_finding, next_evidence, next_retest, next_attack_chain, "
                "next_import, next_assessment FROM engagement_sequences "
                "WHERE engagement_id = 'v5-engagement'"
            )
        ).one()
        candidate = session.execute(
            text(
                "SELECT comparison_id, original_exchange_id, assessment_run_id, check_id, "
                "affected_exchange_ids FROM candidates WHERE id = 'candidate-one'"
            )
        ).one()
        assert sequence == (2, 3, 4, 5, 6, 1)
        assert candidate[:4] == ("comparison-one", "original-request", None, None)
        assert json.loads(candidate.affected_exchange_ids) == []
        assert (
            session.scalar(
                text("SELECT count(*) FROM candidate_replays WHERE candidate_id = 'candidate-one'")
            )
            == 2
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM http_exchanges WHERE engagement_id = 'v5-engagement'")
            )
            == 3
        )
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
