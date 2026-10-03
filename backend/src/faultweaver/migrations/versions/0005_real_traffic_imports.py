"""Add import batches, source metadata, and attack-surface endpoints.

Revision ID: 0005
Revises: 0004
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("engagement_sequences") as batch_op:
        batch_op.add_column(
            sa.Column("next_import", sa.Integer(), nullable=False, server_default=sa.text("1"))
        )
    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("display_id", sa.String(length=24), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("import_format", sa.String(length=24), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("new_endpoint_count", sa.Integer(), nullable=False),
        sa.Column("known_endpoint_count", sa.Integer(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("engagement_id", "display_id", name="uq_import_batch_display_id"),
        sa.UniqueConstraint("engagement_id", "sequence_number", name="uq_import_batch_sequence"),
    )
    op.create_index("ix_import_batches_engagement_id", "import_batches", ["engagement_id"])
    op.create_index("ix_import_batches_import_format", "import_batches", ["import_format"])
    op.create_index("ix_import_batches_content_digest", "import_batches", ["content_digest"])
    op.create_table(
        "attack_surface_endpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("engagement_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("scheme", sa.String(length=12), nullable=True),
        sa.Column("host", sa.String(length=253), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("path_template", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("declared_by_openapi", sa.Boolean(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("engagement_id", "canonical_key", name="uq_attack_surface_key"),
    )
    op.create_index(
        "ix_attack_surface_endpoints_engagement_id",
        "attack_surface_endpoints",
        ["engagement_id"],
    )
    op.create_index("ix_attack_surface_endpoints_method", "attack_surface_endpoints", ["method"])
    op.create_index("ix_attack_surface_endpoints_host", "attack_surface_endpoints", ["host"])
    op.create_index(
        "ix_attack_surface_endpoints_path_template",
        "attack_surface_endpoints",
        ["path_template"],
    )
    with op.batch_alter_table("http_exchanges") as batch_op:
        batch_op.add_column(sa.Column("import_batch_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("endpoint_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("source_entry_index", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_http_exchanges_import_batch",
            "import_batches",
            ["import_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_http_exchanges_endpoint",
            "attack_surface_endpoints",
            ["endpoint_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_http_exchanges_import_batch_id", ["import_batch_id"])
        batch_op.create_index("ix_http_exchanges_endpoint_id", ["endpoint_id"])
    _backfill_existing_endpoints()


def _backfill_existing_endpoints() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, engagement_id, source, method, url, path FROM http_exchanges")
    ).mappings()
    endpoints: dict[tuple[str, str], tuple[str, set[str]]] = {}
    now = datetime.now(UTC)
    for row in rows:
        parsed = urlsplit(row["url"])
        scheme = parsed.scheme.lower() or None
        host = parsed.hostname.lower() if parsed.hostname else None
        try:
            port = parsed.port
        except ValueError:
            port = None
        path = row["path"] or "/"
        key = _canonical_key(row["method"], scheme, host, port, path)
        identity = (row["engagement_id"], key)
        if identity not in endpoints:
            endpoint_id = str(uuid4())
            endpoints[identity] = (endpoint_id, {row["source"]})
            connection.execute(
                sa.text(
                    "INSERT INTO attack_surface_endpoints "
                    "(id, engagement_id, canonical_key, method, scheme, host, port, "
                    "path_template, sources, declared_by_openapi, metadata, "
                    "created_at, updated_at) "
                    "VALUES (:id, :engagement_id, :canonical_key, :method, :scheme, :host, :port, "
                    ":path_template, :sources, 0, :metadata, :created_at, :updated_at)"
                ),
                {
                    "id": endpoint_id,
                    "engagement_id": row["engagement_id"],
                    "canonical_key": key,
                    "method": row["method"],
                    "scheme": scheme,
                    "host": host,
                    "port": port,
                    "path_template": path,
                    "sources": json.dumps([row["source"]]),
                    "metadata": json.dumps({}),
                    "created_at": now,
                    "updated_at": now,
                },
            )
        else:
            endpoint_id, sources = endpoints[identity]
            if row["source"] not in sources:
                sources.add(row["source"])
                connection.execute(
                    sa.text(
                        "UPDATE attack_surface_endpoints SET sources = :sources WHERE id = :id"
                    ),
                    {"id": endpoint_id, "sources": json.dumps(sorted(sources))},
                )
        connection.execute(
            sa.text("UPDATE http_exchanges SET endpoint_id = :endpoint_id WHERE id = :id"),
            {"endpoint_id": endpoint_id, "id": row["id"]},
        )


def _canonical_key(
    method: str, scheme: str | None, host: str | None, port: int | None, path: str
) -> str:
    return "|".join([method.upper(), scheme or "", host or "", str(port or ""), path])


def downgrade() -> None:
    with op.batch_alter_table("http_exchanges") as batch_op:
        batch_op.drop_index("ix_http_exchanges_endpoint_id")
        batch_op.drop_index("ix_http_exchanges_import_batch_id")
        batch_op.drop_constraint("fk_http_exchanges_endpoint", type_="foreignkey")
        batch_op.drop_constraint("fk_http_exchanges_import_batch", type_="foreignkey")
        batch_op.drop_column("source_entry_index")
        batch_op.drop_column("endpoint_id")
        batch_op.drop_column("import_batch_id")
    op.drop_index(
        "ix_attack_surface_endpoints_path_template", table_name="attack_surface_endpoints"
    )
    op.drop_index("ix_attack_surface_endpoints_host", table_name="attack_surface_endpoints")
    op.drop_index("ix_attack_surface_endpoints_method", table_name="attack_surface_endpoints")
    op.drop_index(
        "ix_attack_surface_endpoints_engagement_id", table_name="attack_surface_endpoints"
    )
    op.drop_table("attack_surface_endpoints")
    op.drop_index("ix_import_batches_content_digest", table_name="import_batches")
    op.drop_index("ix_import_batches_import_format", table_name="import_batches")
    op.drop_index("ix_import_batches_engagement_id", table_name="import_batches")
    op.drop_table("import_batches")
    with op.batch_alter_table("engagement_sequences") as batch_op:
        batch_op.drop_column("next_import")
