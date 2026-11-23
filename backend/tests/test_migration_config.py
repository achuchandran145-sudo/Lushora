from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import app.database as database_module


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def _run_upgrade(tmp_path, monkeypatch, env_url=None):
    db_path = tmp_path / "alembic-url-fallback.db"
    expected_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setattr(database_module, "DATABASE_URL", expected_url)

    if env_url is None:
        monkeypatch.delenv("LUSHORA_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("LUSHORA_DATABASE_URL", env_url)

    config = Config(str(ALEMBIC_INI))
    # The repository intentionally leaves this blank; env.py must use the
    # application DATABASE_URL when no environment override is supplied.
    config.set_main_option("sqlalchemy.url", "")
    command.upgrade(config, "head")
    return db_path


def test_alembic_uses_application_database_url_when_environment_is_unset(
    tmp_path, monkeypatch
):
    db_path = _run_upgrade(tmp_path, monkeypatch)

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert inspector.has_table("alembic_version")
        assert inspector.has_table("users")
        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
        assert revision == "0002_admin_recovery"
    finally:
        engine.dispose()


def test_alembic_environment_url_overrides_application_default(
    tmp_path, monkeypatch
):
    env_db_path = tmp_path / "alembic-env-override.db"
    env_url = f"sqlite:///{env_db_path.as_posix()}"
    db_path = _run_upgrade(tmp_path, monkeypatch, env_url=env_url)

    assert db_path == tmp_path / "alembic-url-fallback.db"
    engine = create_engine(env_url)
    try:
        inspector = inspect(engine)
        assert inspector.has_table("alembic_version")
        assert inspector.has_table("users")
        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
        assert revision == "0002_admin_recovery"
    finally:
        engine.dispose()
