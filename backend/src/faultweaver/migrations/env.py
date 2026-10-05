from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from faultweaver.analysis import models as analysis_models  # noqa: F401
from faultweaver.assessments import models as assessment_models  # noqa: F401
from faultweaver.attack_chains import models as attack_chain_models  # noqa: F401
from faultweaver.database import Base
from faultweaver.engagements import models as engagement_models  # noqa: F401
from faultweaver.findings import models as finding_models  # noqa: F401
from faultweaver.http_traffic import models as http_models  # noqa: F401
from faultweaver.identities import models as identity_models  # noqa: F401
from faultweaver.imports import models as import_models  # noqa: F401
from faultweaver.scope import models as scope_models  # noqa: F401
from faultweaver.storage import models as storage_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        context.configure(
            connection=supplied, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
