"""Create or adopt the first Faultweaver schema.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASELINE_COLUMNS = {
    "engagements": {"id", "name", "description", "status", "created_at", "updated_at"},
    "scope_rules": {
        "id",
        "engagement_id",
        "scheme",
        "hostname",
        "port",
        "path_prefix",
        "active",
    },
    "http_exchanges": {
        "id",
        "engagement_id",
        "parent_exchange_id",
        "source",
        "method",
        "url",
        "host",
        "path",
        "query",
        "request_headers",
        "request_body",
        "response_status",
        "response_headers",
        "response_body",
        "response_elapsed_ms",
        "response_truncated",
        "redirect_chain",
        "created_at",
    },
}


def _adopt_existing_baseline() -> bool:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names()) - {"alembic_version"}
    expected = set(_BASELINE_COLUMNS)
    if not existing.intersection(expected):
        return False
    if existing.intersection(expected) != expected:
        missing = ", ".join(sorted(expected - existing))
        raise RuntimeError(f"Cannot adopt a partial Faultweaver schema; missing tables: {missing}")
    for table_name, required_columns in _BASELINE_COLUMNS.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns = required_columns - actual_columns
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise RuntimeError(
                f"Cannot adopt table {table_name}; missing baseline columns: {missing}"
            )
    return True


def upgrade() -> None:
    if _adopt_existing_baseline():
        return

    op.create_table(
        "engagements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scope_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("scheme", sa.String(length=8), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("path_prefix", sa.String(length=2048), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "engagement_id",
            "scheme",
            "hostname",
            "port",
            "path_prefix",
            name="uq_scope_rule",
        ),
    )
    op.create_index("ix_scope_rules_engagement_id", "scope_rules", ["engagement_id"])
    op.create_table(
        "http_exchanges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("parent_exchange_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("request_headers", sa.JSON(), nullable=False),
        sa.Column("request_body", sa.Text(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_headers", sa.JSON(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("response_elapsed_ms", sa.Float(), nullable=True),
        sa.Column("response_truncated", sa.Boolean(), nullable=False),
        sa.Column("redirect_chain", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_exchange_id"], ["http_exchanges.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    indexed_columns = (
        "engagement_id",
        "host",
        "method",
        "parent_exchange_id",
        "path",
        "response_status",
    )
    for column in indexed_columns:
        op.create_index(f"ix_http_exchanges_{column}", "http_exchanges", [column])


def downgrade() -> None:
    indexed_columns = (
        "response_status",
        "path",
        "parent_exchange_id",
        "method",
        "host",
        "engagement_id",
    )
    for column in indexed_columns:
        op.drop_index(f"ix_http_exchanges_{column}", table_name="http_exchanges")
    op.drop_table("http_exchanges")
    op.drop_index("ix_scope_rules_engagement_id", table_name="scope_rules")
    op.drop_table("scope_rules")
    op.drop_table("engagements")
