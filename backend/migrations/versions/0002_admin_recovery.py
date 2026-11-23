"""Add one-use Admin recovery tokens.

Revision ID: 0002_admin_recovery
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_admin_recovery"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # 0001_initial uses the current SQLAlchemy metadata as its create_all()
    # source. On a brand-new database that can include this table already.
    # Existing databases stamped at 0001 do not have it yet.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("admin_recovery_tokens"):
        return

    op.create_table(
        "admin_recovery_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_admin_recovery_tokens_user_id", "admin_recovery_tokens", ["user_id"])
    op.create_index("ix_admin_recovery_tokens_purpose", "admin_recovery_tokens", ["purpose"])
    op.create_index("ix_admin_recovery_tokens_token_digest", "admin_recovery_tokens", ["token_digest"], unique=True)
    op.create_index("ix_admin_recovery_tokens_expires_at", "admin_recovery_tokens", ["expires_at"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("admin_recovery_tokens"):
        return
    existing_indexes = {item["name"] for item in inspector.get_indexes("admin_recovery_tokens")}
    for name in (
        "ix_admin_recovery_tokens_expires_at",
        "ix_admin_recovery_tokens_token_digest",
        "ix_admin_recovery_tokens_purpose",
        "ix_admin_recovery_tokens_user_id",
    ):
        if name in existing_indexes:
            op.drop_index(name, table_name="admin_recovery_tokens")
    op.drop_table("admin_recovery_tokens")
