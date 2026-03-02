"""Alembic environment configuration.

Imports all ORM models so that ``alembic revision --autogenerate`` can
detect schema changes.  The database URL is read from
``config.settings.DATABASE_URL`` at runtime (falls back to the value
in ``alembic.ini``).
"""

from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so that ``config`` and ``src``
# packages can be imported regardless of where Alembic is invoked from.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Import project settings and all model definitions
# ---------------------------------------------------------------------------
from config.settings import DATABASE_URL

# Stocks / financial-data models (legacy declarative_base)
from src.database.models import Base as stocks_base

# News-dashboard models (SQLAlchemy 2.0 DeclarativeBase)
from src.database.repositories.news import _Base as news_base

# ---------------------------------------------------------------------------
# Alembic Config object — provides access to alembic.ini values.
# ---------------------------------------------------------------------------
config = context.config

# Override the .ini URL with the runtime DATABASE_URL so that a single
# environment variable controls both the app and migrations.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Set up Python logging from the config file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Combine metadata from all declarative bases so autogenerate sees every
# table regardless of which Base it was declared on.
# ---------------------------------------------------------------------------
from sqlalchemy import MetaData

combined_metadata = MetaData()

for metadata in (stocks_base.metadata, news_base.metadata):
    for table in metadata.tables.values():
        table.tometadata(combined_metadata)

target_metadata = combined_metadata


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to ``context.execute()`` emit the given SQL string to the
    script output.
    """
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
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
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
