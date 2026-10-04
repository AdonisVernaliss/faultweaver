"""Add bounded crawler and baseline assessment persistence.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("engagement_sequences") as batch_op:
        batch_op.add_column(
            sa.Column("next_assessment", sa.Integer(), nullable=False, server_default=sa.text("1"))
        )
    op.create_table(
        "assessment_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("engagement_id", sa.String(36), nullable=False),
        sa.Column("display_id", sa.String(24), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("max_requests", sa.Integer(), nullable=False),
        sa.Column("requests_per_second", sa.Float(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("request_timeout_seconds", sa.Float(), nullable=False),
        sa.Column("max_response_bytes", sa.Integer(), nullable=False),
        sa.Column("max_query_variants_per_path", sa.Integer(), nullable=False),
        sa.Column("inspect_site_metadata", sa.Boolean(), nullable=False),
        sa.Column("stop_requested", sa.Boolean(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("resource_count", sa.Integer(), nullable=False),
        sa.Column("endpoint_count", sa.Integer(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("failed_request_count", sa.Integer(), nullable=False),
        sa.Column("queued_count", sa.Integer(), nullable=False),
        sa.Column("current_depth", sa.Integer(), nullable=False),
        sa.Column("current_url", sa.Text(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("engagement_id", "display_id", name="uq_assessment_run_display_id"),
        sa.UniqueConstraint("engagement_id", "sequence_number", name="uq_assessment_run_sequence"),
    )
    op.create_index("ix_assessment_runs_engagement_id", "assessment_runs", ["engagement_id"])
    op.create_index("ix_assessment_runs_status", "assessment_runs", ["status"])

    with op.batch_alter_table("http_exchanges") as batch_op:
        batch_op.add_column(sa.Column("assessment_run_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("discovered_from_exchange_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("crawl_depth", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("discovery_kind", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("crawl_error", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_http_exchanges_assessment_run",
            "assessment_runs",
            ["assessment_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_http_exchanges_discovered_from",
            "http_exchanges",
            ["discovered_from_exchange_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_http_exchanges_assessment_run_id", ["assessment_run_id"])
        batch_op.create_index(
            "ix_http_exchanges_discovered_from_exchange_id", ["discovered_from_exchange_id"]
        )

    with op.batch_alter_table("candidates") as batch_op:
        batch_op.alter_column("comparison_id", existing_type=sa.String(36), nullable=True)
        batch_op.add_column(sa.Column("assessment_run_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("endpoint_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("check_id", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("suggested_severity", sa.String(24), nullable=True))
        batch_op.add_column(
            sa.Column("affected_exchange_ids", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.create_foreign_key(
            "fk_candidates_assessment_run",
            "assessment_runs",
            ["assessment_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_candidates_endpoint",
            "attack_surface_endpoints",
            ["endpoint_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_candidates_assessment_run_id", ["assessment_run_id"])
        batch_op.create_index("ix_candidates_endpoint_id", ["endpoint_id"])
        batch_op.create_index("ix_candidates_check_id", ["check_id"])

    op.create_table(
        "crawl_discoveries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("assessment_run_id", sa.String(36), nullable=False),
        sa.Column("parent_exchange_id", sa.String(36), nullable=True),
        sa.Column("requested_exchange_id", sa.String(36), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assessment_run_id"], ["assessment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_exchange_id"], ["http_exchanges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["requested_exchange_id"], ["http_exchanges.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_run_id", "canonical_url", name="uq_crawl_discovery_url"),
    )
    op.create_index(
        "ix_crawl_discoveries_assessment_run_id", "crawl_discoveries", ["assessment_run_id"]
    )
    op.create_index(
        "ix_crawl_discoveries_parent_exchange_id", "crawl_discoveries", ["parent_exchange_id"]
    )
    op.create_index(
        "ix_crawl_discoveries_requested_exchange_id", "crawl_discoveries", ["requested_exchange_id"]
    )
    op.create_index("ix_crawl_discoveries_state", "crawl_discoveries", ["state"])

    op.create_table(
        "crawl_forms",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("assessment_run_id", sa.String(36), nullable=False),
        sa.Column("exchange_id", sa.String(36), nullable=False),
        sa.Column("action_url", sa.Text(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("enctype", sa.String(120), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assessment_run_id"], ["assessment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exchange_id"], ["http_exchanges.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crawl_forms_assessment_run_id", "crawl_forms", ["assessment_run_id"])
    op.create_index("ix_crawl_forms_exchange_id", "crawl_forms", ["exchange_id"])

    op.create_table(
        "baseline_observations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("assessment_run_id", sa.String(36), nullable=False),
        sa.Column("exchange_id", sa.String(36), nullable=True),
        sa.Column("endpoint_id", sa.String(36), nullable=True),
        sa.Column("candidate_id", sa.String(36), nullable=True),
        sa.Column("check_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.Column("suggested_severity", sa.String(24), nullable=False),
        sa.Column("fingerprint", sa.String(200), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("affected_exchange_ids", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assessment_run_id"], ["assessment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exchange_id"], ["http_exchanges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["endpoint_id"], ["attack_surface_endpoints.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_run_id", "fingerprint", name="uq_baseline_observation"),
    )
    op.create_index(
        "ix_baseline_observations_assessment_run_id", "baseline_observations", ["assessment_run_id"]
    )
    op.create_index(
        "ix_baseline_observations_exchange_id", "baseline_observations", ["exchange_id"]
    )
    op.create_index(
        "ix_baseline_observations_endpoint_id", "baseline_observations", ["endpoint_id"]
    )
    op.create_index(
        "ix_baseline_observations_candidate_id", "baseline_observations", ["candidate_id"]
    )
    op.create_index("ix_baseline_observations_check_id", "baseline_observations", ["check_id"])
    op.create_index(
        "ix_baseline_observations_classification", "baseline_observations", ["classification"]
    )


def downgrade() -> None:
    op.drop_table("baseline_observations")
    op.drop_table("crawl_forms")
    op.drop_table("crawl_discoveries")
    with op.batch_alter_table("candidates") as batch_op:
        batch_op.drop_index("ix_candidates_check_id")
        batch_op.drop_index("ix_candidates_endpoint_id")
        batch_op.drop_index("ix_candidates_assessment_run_id")
        batch_op.drop_constraint("fk_candidates_endpoint", type_="foreignkey")
        batch_op.drop_constraint("fk_candidates_assessment_run", type_="foreignkey")
        batch_op.drop_column("affected_exchange_ids")
        batch_op.drop_column("suggested_severity")
        batch_op.drop_column("check_id")
        batch_op.drop_column("endpoint_id")
        batch_op.drop_column("assessment_run_id")
        batch_op.alter_column("comparison_id", existing_type=sa.String(36), nullable=False)
    with op.batch_alter_table("http_exchanges") as batch_op:
        batch_op.drop_index("ix_http_exchanges_discovered_from_exchange_id")
        batch_op.drop_index("ix_http_exchanges_assessment_run_id")
        batch_op.drop_constraint("fk_http_exchanges_discovered_from", type_="foreignkey")
        batch_op.drop_constraint("fk_http_exchanges_assessment_run", type_="foreignkey")
        batch_op.drop_column("crawl_error")
        batch_op.drop_column("discovery_kind")
        batch_op.drop_column("crawl_depth")
        batch_op.drop_column("discovered_from_exchange_id")
        batch_op.drop_column("assessment_run_id")
    op.drop_index("ix_assessment_runs_status", table_name="assessment_runs")
    op.drop_index("ix_assessment_runs_engagement_id", table_name="assessment_runs")
    op.drop_table("assessment_runs")
    with op.batch_alter_table("engagement_sequences") as batch_op:
        batch_op.drop_column("next_assessment")
