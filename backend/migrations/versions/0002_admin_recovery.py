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
    op.drop_index("ix_admin_recovery_tokens_expires_at", table_name="admin_recovery_tokens")
    op.drop_index("ix_admin_recovery_tokens_token_digest", table_name="admin_recovery_tokens")
    op.drop_index("ix_admin_recovery_tokens_purpose", table_name="admin_recovery_tokens")
    op.drop_index("ix_admin_recovery_tokens_user_id", table_name="admin_recovery_tokens")
    op.drop_table("admin_recovery_tokens")
