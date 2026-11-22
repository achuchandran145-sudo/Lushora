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
    if not DATABASE_URL.startswith('sqlite'):
        return
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    with engine.begin() as conn:
        provider_cols = {c['name'] for c in inspector.get_columns('providers')}
        if 'owner_user_id' not in provider_cols:
            conn.execute(text('ALTER TABLE providers ADD COLUMN owner_user_id INTEGER'))
        if 'approval_status' not in provider_cols:
            conn.execute(text("ALTER TABLE providers ADD COLUMN approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'"))
        user_cols = {c['name'] for c in inspector.get_columns('users')}
        for col, sql in [('first_name', 'ALTER TABLE users ADD COLUMN first_name VARCHAR(80) NOT NULL DEFAULT \'\''), ('last_name', 'ALTER TABLE users ADD COLUMN last_name VARCHAR(80) NOT NULL DEFAULT \'\''), ('street_address', 'ALTER TABLE users ADD COLUMN street_address TEXT NOT NULL DEFAULT \'\''), ('city', 'ALTER TABLE users ADD COLUMN city VARCHAR(80) NOT NULL DEFAULT \'\''), ('locality', 'ALTER TABLE users ADD COLUMN locality VARCHAR(120) NOT NULL DEFAULT \'\'')]:
            if col not in user_cols:
                conn.execute(text(sql))

        delivery_cols = {c['name'] for c in inspector.get_columns('notification_deliveries')} if 'notification_deliveries' in inspector.get_table_names() else set()
        if 'next_attempt_at' not in delivery_cols:
            conn.execute(text('ALTER TABLE notification_deliveries ADD COLUMN next_attempt_at DATETIME'))
        device_cols = {c['name'] for c in inspector.get_columns('notification_devices')} if 'notification_devices' in inspector.get_table_names() else set()
        # Revoke legacy implicit external consent once; users can explicitly opt in afterward.
        if 'notification_preferences' in inspector.get_table_names():
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
        booking_cols = {c['name'] for c in inspector.get_columns('bookings')}
        if 'customer_user_id' not in booking_cols:
            conn.execute(text('ALTER TABLE bookings ADD COLUMN customer_user_id INTEGER'))
