from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text


def validate_database_revision(connection) -> None:
    """Fail startup unless the database is at every repository migration head."""
    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        raise RuntimeError(
            "Production database migrations are missing. "
            "Run backend/scripts/migrate_production.sh before starting the API."
        )

    applied = {
        row[0]
        for row in connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).fetchall()
    }
    if not applied:
        raise RuntimeError(
            "Production database has no applied Alembic migration revision."
        )

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    expected = set(ScriptDirectory.from_config(config).get_heads())

    if not expected:
        raise RuntimeError("No Alembic migration head is configured in the application.")

    if applied != expected:
        applied_text = ", ".join(sorted(applied))
        expected_text = ", ".join(sorted(expected))
        raise RuntimeError(
            "Production database migrations are not at the latest revision. "
            f"Applied: [{applied_text}]. Expected: [{expected_text}]. "
            "Run backend/scripts/migrate_production.sh before starting the API."
        )
