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
        booking_cols = {c['name'] for c in inspector.get_columns('bookings')}
        if 'customer_user_id' not in booking_cols:
            conn.execute(text('ALTER TABLE bookings ADD COLUMN customer_user_id INTEGER'))
