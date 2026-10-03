"""Add operator-authored attack chains and ordered steps.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("engagement_sequences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "next_attack_chain", sa.Integer(), nullable=False, server_default=sa.text("1")
            )
        )
    op.create_table(
        "attack_chains",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("display_id", sa.String(length=24), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resulting_impact", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("engagement_id", "display_id", name="uq_attack_chain_display_id"),
        sa.UniqueConstraint("engagement_id", "sequence_number", name="uq_attack_chain_sequence"),
    )
    op.create_index("ix_attack_chains_engagement_id", "attack_chains", ["engagement_id"])
    op.create_table(
        "attack_chain_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attack_chain_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=24), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(step_type = 'Finding' AND finding_id IS NOT NULL) OR "
            "(step_type = 'Intermediate' AND finding_id IS NULL)",
            name="ck_attack_chain_step_type",
        ),
        sa.ForeignKeyConstraint(["attack_chain_id"], ["attack_chains.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attack_chain_id", "position", name="uq_attack_chain_step_position"),
    )
    op.create_index(
        "ix_attack_chain_steps_attack_chain_id", "attack_chain_steps", ["attack_chain_id"]
    )
    op.create_index("ix_attack_chain_steps_finding_id", "attack_chain_steps", ["finding_id"])
    op.create_table(
        "attack_chain_evidence",
        sa.Column("attack_chain_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["attack_chain_id"], ["attack_chains.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("attack_chain_id", "evidence_id"),
    )
    op.create_table(
        "attack_chain_step_evidence",
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["step_id"], ["attack_chain_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("step_id", "evidence_id"),
    )
    op.create_table(
        "attack_chain_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attack_chain_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attack_chain_id"], ["attack_chains.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attack_chain_history_attack_chain_id", "attack_chain_history", ["attack_chain_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_attack_chain_history_attack_chain_id", table_name="attack_chain_history")
    op.drop_table("attack_chain_history")
    op.drop_table("attack_chain_step_evidence")
    op.drop_table("attack_chain_evidence")
    op.drop_index("ix_attack_chain_steps_finding_id", table_name="attack_chain_steps")
    op.drop_index("ix_attack_chain_steps_attack_chain_id", table_name="attack_chain_steps")
    op.drop_table("attack_chain_steps")
    op.drop_index("ix_attack_chains_engagement_id", table_name="attack_chains")
    op.drop_table("attack_chains")
    with op.batch_alter_table("engagement_sequences") as batch_op:
        batch_op.drop_column("next_attack_chain")
