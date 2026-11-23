from sqlalchemy import create_engine, inspect, text

import app.database as database_module


def test_sqlite_provider_upgrade_adds_legacy_columns_and_is_repeatable(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "legacy-providers.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE providers (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    category VARCHAR(40) NOT NULL,
                    city VARCHAR(80) NOT NULL,
                    locality VARCHAR(100) NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    verified BOOLEAN NOT NULL DEFAULT 0,
                    rating FLOAT NOT NULL DEFAULT 0.0
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO providers
                    (id, name, category, city, locality, description, verified, rating)
                VALUES
                    (7, 'Legacy Salon', 'Salon', 'Coimbatore', 'Vadavalli',
                     'Existing provider record', 1, 4.5)
                """
            )
        )

    monkeypatch.setattr(database_module, "engine", engine)
    monkeypatch.setattr(
        database_module, "DATABASE_URL", f"sqlite:///{db_path.as_posix()}"
    )

    try:
        database_module.migrate_sqlite_schema()
        # A second invocation must remain safe and must not duplicate columns.
        database_module.migrate_sqlite_schema()

        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("providers")}
        assert {
            "owner_user_id",
            "approval_status",
            "availability_config",
            "booking_lock_version",
        }.issubset(columns)

        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, name, city, locality, verified, rating,
                           approval_status, availability_config, booking_lock_version
                    FROM providers
                    WHERE id = 7
                    """
                )
            ).one()

        assert row.id == 7
        assert row.name == "Legacy Salon"
        assert row.city == "Coimbatore"
        assert row.locality == "Vadavalli"
        assert bool(row.verified) is True
        assert row.rating == 4.5
        assert row.approval_status == "approved"
        assert row.availability_config == "{}"
        assert row.booking_lock_version == 0
    finally:
        engine.dispose()


def test_sqlite_provider_unique_owner_rebuild_preserves_services(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "legacy-unique-provider-owner.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO users (id) VALUES (9)"))
        connection.execute(
            text(
                """
                CREATE TABLE providers (
                    id INTEGER PRIMARY KEY,
                    owner_user_id INTEGER UNIQUE REFERENCES users(id),
                    name VARCHAR(120) NOT NULL,
                    category VARCHAR(40) NOT NULL,
                    city VARCHAR(80) NOT NULL,
                    locality VARCHAR(100) NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    verified BOOLEAN NOT NULL DEFAULT 0,
                    rating FLOAT NOT NULL DEFAULT 0.0,
                    availability_config TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO providers
                    (id, owner_user_id, name, category, city, locality,
                     description, verified, rating)
                VALUES
                    (12, 9, 'Multi Category Studio', 'Salon', 'Coimbatore',
                     'Vadavalli', 'Legacy owner listing', 1, 4.8)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE services (
                    id INTEGER PRIMARY KEY,
                    provider_id INTEGER NOT NULL REFERENCES providers(id),
                    name VARCHAR(120) NOT NULL,
                    price_inr INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO services (id, provider_id, name, price_inr) "
                "VALUES (55, 12, 'Haircut', 500)"
            )
        )

    monkeypatch.setattr(database_module, "engine", engine)
    monkeypatch.setattr(
        database_module, "DATABASE_URL", f"sqlite:///{db_path.as_posix()}"
    )

    try:
        database_module.migrate_sqlite_schema()

        with engine.connect() as connection:
            provider = connection.execute(
                text(
                    """
                    SELECT id, owner_user_id, name, approval_status,
                           availability_config, booking_lock_version
                    FROM providers WHERE id = 12
                    """
                )
            ).one()
            service = connection.execute(
                text(
                    "SELECT id, provider_id, name, price_inr "
                    "FROM services WHERE id = 55"
                )
            ).one()

        assert provider.id == 12
        assert provider.owner_user_id == 9
        assert provider.name == "Multi Category Studio"
        assert provider.approval_status == "approved"
        assert provider.availability_config == "{}"
        assert provider.booking_lock_version == 0
        assert service.id == 55
        assert service.provider_id == provider.id
        assert service.name == "Haircut"
        assert service.price_inr == 500

        unique_constraints = inspect(engine).get_unique_constraints("providers")
        assert not any(
            set(constraint.get("column_names") or []) == {"owner_user_id"}
            for constraint in unique_constraints
        )
    finally:
        engine.dispose()
