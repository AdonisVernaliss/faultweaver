"""Add finding, immutable evidence, notes, retests, and lifecycle history.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("identities") as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("candidates") as batch_op:
        batch_op.add_column(sa.Column("review_decision", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "engagement_sequences",
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("next_finding", sa.Integer(), nullable=False),
        sa.Column("next_evidence", sa.Integer(), nullable=False),
        sa.Column("next_retest", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("engagement_id"),
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO engagement_sequences "
            "(engagement_id, next_finding, next_evidence, next_retest) "
            "SELECT id, 1, 1, 1 FROM engagements"
        )
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("display_id", sa.String(length=24), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("affected_asset", sa.String(length=500), nullable=False),
        sa.Column("affected_endpoints", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=False),
        sa.Column("reproduction_steps", sa.JSON(), nullable=False),
        sa.Column("remediation", sa.Text(), nullable=False),
        sa.Column("references", sa.JSON(), nullable=False),
        sa.Column("supporting_original_exchange_id", sa.String(length=36), nullable=True),
        sa.Column("supporting_comparison_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["supporting_comparison_id"], ["response_comparisons.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["supporting_original_exchange_id"], ["http_exchanges.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id"),
        sa.UniqueConstraint("engagement_id", "display_id", name="uq_finding_display_id"),
        sa.UniqueConstraint("engagement_id", "sequence_number", name="uq_finding_sequence"),
    )
    op.create_index("ix_findings_engagement_id", "findings", ["engagement_id"])
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("display_id", sa.String(length=24), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("source_exchange_id", sa.String(length=36), nullable=True),
        sa.Column("source_comparison_id", sa.String(length=36), nullable=True),
        sa.Column("source_candidate_id", sa.String(length=36), nullable=True),
        sa.Column("finding_id", sa.String(length=36), nullable=True),
        sa.Column("author_label", sa.String(length=80), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_candidate_id"], ["candidates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_comparison_id"], ["response_comparisons.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["source_exchange_id"], ["http_exchanges.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("engagement_id", "display_id", name="uq_evidence_display_id"),
        sa.UniqueConstraint("engagement_id", "sequence_number", name="uq_evidence_sequence"),
    )
    op.create_index("ix_evidence_engagement_id", "evidence", ["engagement_id"])
    op.create_index("ix_evidence_finding_id", "evidence", ["finding_id"])
    op.create_table(
        "retests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("display_id", sa.String(length=24), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("engagement_id", "display_id", name="uq_retest_display_id"),
        sa.UniqueConstraint("engagement_id", "sequence_number", name="uq_retest_sequence"),
    )
    op.create_index("ix_retests_engagement_id", "retests", ["engagement_id"])
    op.create_index("ix_retests_finding_id", "retests", ["finding_id"])
    op.create_table(
        "retest_evidence",
        sa.Column("retest_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retest_id"], ["retests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("retest_id", "evidence_id"),
    )
    op.create_table(
        "operator_notes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("finding_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_id", sa.String(length=36), nullable=True),
        sa.Column("retest_id", sa.String(length=36), nullable=True),
        sa.Column("author_label", sa.String(length=80), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(candidate_id IS NOT NULL) + (finding_id IS NOT NULL) + "
            "(evidence_id IS NOT NULL) + (retest_id IS NOT NULL) = 1",
            name="ck_operator_note_one_target",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retest_id"], ["retests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operator_notes_engagement_id", "operator_notes", ["engagement_id"])
    op.create_table(
        "finding_lifecycle_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finding_lifecycle_events_finding_id", "finding_lifecycle_events", ["finding_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_finding_lifecycle_events_finding_id", table_name="finding_lifecycle_events")
    op.drop_table("finding_lifecycle_events")
    op.drop_index("ix_operator_notes_engagement_id", table_name="operator_notes")
    op.drop_table("operator_notes")
    op.drop_table("retest_evidence")
    op.drop_index("ix_retests_finding_id", table_name="retests")
    op.drop_index("ix_retests_engagement_id", table_name="retests")
    op.drop_table("retests")
    op.drop_index("ix_evidence_finding_id", table_name="evidence")
    op.drop_index("ix_evidence_engagement_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_findings_engagement_id", table_name="findings")
    op.drop_table("findings")
    op.drop_table("engagement_sequences")
    with op.batch_alter_table("candidates") as batch_op:
        batch_op.drop_column("archived_at")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("review_decision")
    with op.batch_alter_table("identities") as batch_op:
        batch_op.drop_column("archived_at")
