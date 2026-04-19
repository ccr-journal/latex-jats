"""Alembic environment — wires SQLModel metadata for autogenerate support."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Populate SQLModel metadata with all table classes. When alembic is invoked
# from *inside* the running FastAPI app (startup stamp), the models module is
# already loaded as `web.backend.app.models`; importing it here under the
# alternate name `app.models` would register the same tables twice on the
# shared SQLModel.metadata and raise InvalidRequestError. So prefer the
# package path the running app uses, and only fall back to the plain `app.*`
# path when running alembic standalone from web/backend/.
try:
    from web.backend.app.models import (  # noqa: F401
        AccessToken,
        Manuscript,
        ManuscriptAuthor,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from app.models import (  # noqa: F401
        AccessToken,
        Manuscript,
        ManuscriptAuthor,
    )

config = context.config
target_metadata = SQLModel.metadata

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
