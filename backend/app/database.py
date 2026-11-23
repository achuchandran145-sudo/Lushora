import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("LUSHORA_DATABASE_URL", "sqlite:///./lushora.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Lightweight SQLite migration helper for the local MVP database. Production deployments should use Alembic.
def migrate_sqlite_schema():
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA defer_foreign_keys=ON"))
        table_names = set(inspector.get_table_names())
        if "providers" in table_names:
            provider_cols = {c["name"] for c in inspector.get_columns("providers")}
            if "owner_user_id" not in provider_cols:
                conn.execute(text("ALTER TABLE providers ADD COLUMN owner_user_id INTEGER"))
            if "approval_status" not in provider_cols:
                conn.execute(text("ALTER TABLE providers ADD COLUMN approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'"))
            if "availability_config" not in provider_cols:
                conn.execute(text("ALTER TABLE providers ADD COLUMN availability_config TEXT NOT NULL DEFAULT '{}'"))

            # Older MVP schema enforced one provider per owner. Verification approval now
            # creates one provider listing per selected category, so remove that legacy
            # constraint while preserving provider IDs and all dependent service rows.
            owner_unique = any(
                set(index.get("column_names") or []) == {"owner_user_id"}
                and index.get("unique")
                for index in inspector.get_indexes("providers")
            ) or any(
                set(constraint.get("column_names") or []) == {"owner_user_id"}
                for constraint in inspector.get_unique_constraints("providers")
            )
            if owner_unique:
                conn.execute(text("""
                    CREATE TABLE providers_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        owner_user_id INTEGER,
                        approval_status VARCHAR(20) NOT NULL DEFAULT 'approved',
                        name VARCHAR(120) NOT NULL,
                        category VARCHAR(40) NOT NULL,
                        city VARCHAR(80) NOT NULL,
                        locality VARCHAR(100) NOT NULL DEFAULT '',
                        description TEXT NOT NULL DEFAULT '',
                        verified BOOLEAN NOT NULL DEFAULT 0,
                        rating FLOAT NOT NULL DEFAULT 0.0,
                        availability_config TEXT NOT NULL DEFAULT '{}',
                        booking_lock_version INTEGER NOT NULL DEFAULT 0,
                        FOREIGN KEY(owner_user_id) REFERENCES users(id)
                    )
                """))
                conn.execute(text("""
                    INSERT INTO providers_new
                    (id, owner_user_id, approval_status, name, category, city, locality,
                     description, verified, rating, availability_config)
                    SELECT id, owner_user_id, approval_status, name, category, city, locality,
                           description, verified, rating, availability_config
                    FROM providers
                """))
                conn.execute(text("DROP TABLE providers"))
                conn.execute(text("ALTER TABLE providers_new RENAME TO providers"))
                conn.execute(text("CREATE INDEX ix_providers_id ON providers (id)"))
                conn.execute(text("CREATE INDEX ix_providers_approval_status ON providers (approval_status)"))
                conn.execute(text("CREATE INDEX ix_providers_category ON providers (category)"))
                conn.execute(text("CREATE INDEX ix_providers_city ON providers (city)"))

        if "auth_rate_limit_entries" in table_names:
            # Repair legacy development databases that created the rate-limit table
            # before the composite uniqueness constraint was introduced.
            conn.execute(text("""
                DELETE FROM auth_rate_limit_entries
                WHERE id NOT IN (
                    SELECT MIN(id) FROM auth_rate_limit_entries
                    GROUP BY scope, identifier_hash
                )
            """))
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_rate_limit_scope_identifier
                ON auth_rate_limit_entries (scope, identifier_hash)
            """))

        user_cols = {c["name"] for c in inspector.get_columns("users")} if "users" in table_names else set()
        if "users" in table_names and "auth_token_version" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN auth_token_version INTEGER NOT NULL DEFAULT 0"))
        for col, sql in [
            ("first_name", "ALTER TABLE users ADD COLUMN first_name VARCHAR(80) NOT NULL DEFAULT ''"),
            ("last_name", "ALTER TABLE users ADD COLUMN last_name VARCHAR(80) NOT NULL DEFAULT ''"),
            ("street_address", "ALTER TABLE users ADD COLUMN street_address TEXT NOT NULL DEFAULT ''"),
            ("city", "ALTER TABLE users ADD COLUMN city VARCHAR(80) NOT NULL DEFAULT ''"),
            ("locality", "ALTER TABLE users ADD COLUMN locality VARCHAR(120) NOT NULL DEFAULT ''"),
        ]:
            if "users" in table_names and col not in user_cols:
                conn.execute(text(sql))

        if "notification_deliveries" in table_names:
            delivery_cols = {c["name"] for c in inspector.get_columns("notification_deliveries")}
            if "next_attempt_at" not in delivery_cols:
                conn.execute(text("ALTER TABLE notification_deliveries ADD COLUMN next_attempt_at DATETIME"))
        # Revoke legacy implicit external consent once; users can explicitly opt in afterward.
        if "notification_preferences" in table_names:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_key VARCHAR(120) PRIMARY KEY,
                    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            already = conn.execute(text("SELECT 1 FROM schema_migrations WHERE migration_key='notification_external_opt_in_defaults_v1'")).first()
            if not already:
                conn.execute(text("UPDATE notification_preferences SET push_enabled=0, whatsapp_enabled=0, sms_enabled=0"))
                conn.execute(text("INSERT INTO schema_migrations (migration_key) VALUES ('notification_external_opt_in_defaults_v1')"))
        payment_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(payments)").fetchall()} if "payments" in table_names else set()
        if "payments" in table_names and "payment_type" not in payment_cols:
            conn.execute(text("ALTER TABLE payments ADD COLUMN payment_type VARCHAR(20) NOT NULL DEFAULT 'full'"))
        if "payments" in table_names and "balance_due_inr" not in payment_cols:
            conn.execute(text("ALTER TABLE payments ADD COLUMN balance_due_inr INTEGER NOT NULL DEFAULT 0"))
        for col,sql in [("gateway_order_id","ALTER TABLE payments ADD COLUMN gateway_order_id VARCHAR(120) NOT NULL DEFAULT ''"),("gateway_payment_id","ALTER TABLE payments ADD COLUMN gateway_payment_id VARCHAR(120) NOT NULL DEFAULT ''"),("receipt_number","ALTER TABLE payments ADD COLUMN receipt_number VARCHAR(40) NOT NULL DEFAULT ''")]:
            if "payments" in table_names and col not in payment_cols:
                conn.execute(text(sql))
        booking_cols = {c["name"] for c in inspector.get_columns("bookings")} if "bookings" in table_names else set()
        if "bookings" in table_names:
            if "customer_user_id" not in booking_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN customer_user_id INTEGER"))
            if "expires_at" not in booking_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN expires_at DATETIME"))
            if "staff_id" not in booking_cols:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN staff_id INTEGER REFERENCES provider_staff(id)"))
        provider_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(providers)").fetchall()} if "providers" in table_names else set()
        if "providers" in table_names and "booking_lock_version" not in provider_cols:
            conn.execute(text("ALTER TABLE providers ADD COLUMN booking_lock_version INTEGER NOT NULL DEFAULT 0"))
