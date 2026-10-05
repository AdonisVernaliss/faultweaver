"""Record the protected-storage policy inside the encrypted database.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "storage_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("cipher_format", sa.Integer(), nullable=False),
        sa.Column("key_id", sa.String(32), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_storage_metadata_singleton"),
    )


def downgrade() -> None:
    raise RuntimeError("Protected-storage downgrade is not supported")
