from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool
from alembic import context

from app.database import Base, DATABASE_URL
from app import models  # noqa: F401


config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Resolve the Alembic URL using the same default as the application.

    Environment variables take precedence, followed by alembic.ini, then the
    application's configured DATABASE_URL. Empty environment variables and
    empty ini values are treated as unset rather than passed to SQLAlchemy.
    """
    url = (
        os.getenv("LUSHORA_DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
        or DATABASE_URL
    )
    url = url.strip() if url else ""
    if not url:
        raise RuntimeError(
            "Database URL is not configured. Set LUSHORA_DATABASE_URL "
            "or sqlalchemy.url in alembic.ini."
        )
    return url


def run_migrations_offline():
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
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
