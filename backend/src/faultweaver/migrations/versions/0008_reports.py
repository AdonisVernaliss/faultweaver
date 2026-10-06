"""Add operator report drafts and immutable canonical revisions.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "engagement_sequences",
        sa.Column("next_report", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "engagement_id",
            sa.String(36),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_id", sa.String(24), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("revision_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("engagement_id", "display_id", name="uq_report_display_id"),
    )
    op.create_index("ix_reports_engagement_id", "reports", ["engagement_id"])
    op.create_table(
        "report_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(36),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.UniqueConstraint("report_id", "revision", name="uq_report_revision"),
    )
    op.create_index("ix_report_revisions_report_id", "report_revisions", ["report_id"])


def downgrade() -> None:
    op.drop_table("report_revisions")
    op.drop_table("reports")
    with op.batch_alter_table("engagement_sequences") as batch:
        batch.drop_column("next_report")
