"""Initial schema baseline.

This first migration creates the SQLAlchemy model schema. Subsequent changes
must be added as incremental Alembic revisions; do not edit this baseline
after it has been applied to a deployed database.
"""
from alembic import op
from app.database import Base
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
