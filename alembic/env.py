import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

# Ensure application root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import Base and ensure all models are registered in Base.metadata
from app.db.base import Base
import app.models  # Registers Category, Product, Image, AIGeneration, ProductMetadata
from app.db.database import DATABASE_URL, engine

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata points directly to existing SQLAlchemy Base.metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    """
    url = str(DATABASE_URL)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Associates a connection with the context. Defaults to the application's
    existing engine, while allowing override for tests or custom connections.
    """
    connectable = config.attributes.get("connection", None)
    if connectable is None:
        custom_url = config.get_main_option("sqlalchemy.url")
        if custom_url and custom_url.strip() and not custom_url.startswith("driver://"):
            from sqlalchemy import create_engine
            connectable = create_engine(custom_url)
        else:
            connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
