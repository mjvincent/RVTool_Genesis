"""Alembic environment configuration for RVTool Genesis."""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make api/ importable so we can import our models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all models so Alembic autogenerate can detect them
from db.database import Base  # noqa: E402
import db.models  # noqa: E402, F401 — side-effect import registers all models

# Alembic Config object — provides access to the .ini file values
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for --autogenerate
target_metadata = Base.metadata

# Derive a synchronous psycopg2 URL from DATABASE_URL
# (Alembic does not support asyncpg directly)
_raw_url: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://rvtool:rvtool_password@db:5432/rvtooldb",
)
# Strip +asyncpg if present so psycopg2 is used for migrations
_sync_url: str = _raw_url.replace("+asyncpg", "")

config.set_main_option("sqlalchemy.url", _sync_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required)."""
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
    """Run migrations in 'online' mode (live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
