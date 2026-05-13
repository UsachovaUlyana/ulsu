"""Alembic env — uses sync psycopg2 driver for migration execution.

Runtime app uses asyncpg, but migrations are sync; we translate the URL.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_db_url() -> str:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_bot",
    )
    return url.replace("+asyncpg", "+psycopg2")


config.set_main_option("sqlalchemy.url", _sync_db_url())

target_metadata = None  # we use raw SQL in migrations


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
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
