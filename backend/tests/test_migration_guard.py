import pytest
from sqlalchemy import create_engine, text

from app.migration_guard import validate_database_revision


def _database(tmp_path, revision=None):
    engine = create_engine(f"sqlite:///{(tmp_path / 'migration-guard.db').as_posix()}")
    if revision is not None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE alembic_version "
                    "(version_num VARCHAR(32) NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": revision},
            )
    return engine


def test_production_migration_guard_rejects_missing_version_table(tmp_path):
    engine = _database(tmp_path)
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match="migrations are missing"):
                validate_database_revision(connection)
    finally:
        engine.dispose()


def test_production_migration_guard_rejects_outdated_revision(tmp_path):
    engine = _database(tmp_path, "0001_initial")
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match="not at the latest revision"):
                validate_database_revision(connection)
    finally:
        engine.dispose()


def test_production_migration_guard_accepts_current_revision(tmp_path):
    engine = _database(tmp_path, "0002_admin_recovery")
    try:
        with engine.connect() as connection:
            validate_database_revision(connection)
    finally:
        engine.dispose()
