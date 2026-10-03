"""Add identity contexts and differential analysis records.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False),
        sa.Column("bearer_token", sa.Text(), nullable=True),
        sa.Column("api_key_header", sa.String(length=160), nullable=True),
        sa.Column("api_key_value", sa.Text(), nullable=True),
        sa.Column("cookies", sa.JSON(), nullable=False),
        sa.Column("custom_headers", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("engagement_id", "name", name="uq_identity_engagement_name"),
    )
    op.create_index("ix_identities_engagement_id", "identities", ["engagement_id"])

    connection = op.get_bind()
    now = datetime.now(UTC)
    engagement_ids = connection.execute(sa.text("SELECT id FROM engagements")).scalars()
    identity_table = sa.table(
        "identities",
        sa.column("id", sa.String()),
        sa.column("engagement_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_anonymous", sa.Boolean()),
        sa.column("bearer_token", sa.Text()),
        sa.column("api_key_header", sa.String()),
        sa.column("api_key_value", sa.Text()),
        sa.column("cookies", sa.JSON()),
        sa.column("custom_headers", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for engagement_id in engagement_ids:
        connection.execute(
            identity_table.insert().values(
                id=str(uuid4()),
                engagement_id=engagement_id,
                name="Anonymous",
                description="No authentication material",
                is_anonymous=True,
                bearer_token=None,
                api_key_header=None,
                api_key_value=None,
                cookies=[],
                custom_headers=[],
                created_at=now,
                updated_at=now,
            )
        )

    with op.batch_alter_table("http_exchanges") as batch_op:
        batch_op.add_column(sa.Column("identity_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "auth_source", sa.String(length=24), nullable=False, server_default="original"
            )
        )
        batch_op.add_column(
            sa.Column("operator_modified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_foreign_key(
            "fk_http_exchanges_identity_id",
            "identities",
            ["identity_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_http_exchanges_identity_id", ["identity_id"])

    op.create_table(
        "response_comparisons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("original_exchange_id", sa.String(length=36), nullable=False),
        sa.Column("replay_a_id", sa.String(length=36), nullable=False),
        sa.Column("replay_b_id", sa.String(length=36), nullable=False),
        sa.Column("identity_a_id", sa.String(length=36), nullable=False),
        sa.Column("identity_b_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["identity_a_id"], ["identities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["identity_b_id"], ["identities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["original_exchange_id"], ["http_exchanges.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["replay_a_id"], ["http_exchanges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replay_b_id"], ["http_exchanges.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "engagement_id",
        "identity_a_id",
        "identity_b_id",
        "original_exchange_id",
        "replay_a_id",
        "replay_b_id",
    ):
        op.create_index(f"ix_response_comparisons_{column}", "response_comparisons", [column])

    op.create_table(
        "candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("comparison_id", sa.String(length=36), nullable=False),
        sa.Column("original_exchange_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reasoning", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comparison_id"], ["response_comparisons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["original_exchange_id"], ["http_exchanges.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comparison_id"),
    )
    op.create_index("ix_candidates_engagement_id", "candidates", ["engagement_id"])
    op.create_index("ix_candidates_original_exchange_id", "candidates", ["original_exchange_id"])
    op.create_table(
        "candidate_replays",
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("exchange_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exchange_id"], ["http_exchanges.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_id", "exchange_id"),
    )


def downgrade() -> None:
    op.drop_table("candidate_replays")
    op.drop_index("ix_candidates_original_exchange_id", table_name="candidates")
    op.drop_index("ix_candidates_engagement_id", table_name="candidates")
    op.drop_table("candidates")
    for column in (
        "replay_b_id",
        "replay_a_id",
        "original_exchange_id",
        "identity_b_id",
        "identity_a_id",
        "engagement_id",
    ):
        op.drop_index(f"ix_response_comparisons_{column}", table_name="response_comparisons")
    op.drop_table("response_comparisons")
    with op.batch_alter_table("http_exchanges") as batch_op:
        batch_op.drop_index("ix_http_exchanges_identity_id")
        batch_op.drop_constraint("fk_http_exchanges_identity_id", type_="foreignkey")
        batch_op.drop_column("operator_modified")
        batch_op.drop_column("auth_source")
        batch_op.drop_column("identity_id")
    op.drop_index("ix_identities_engagement_id", table_name="identities")
    op.drop_table("identities")
