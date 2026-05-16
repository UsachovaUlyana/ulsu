"""users.referred_by ON DELETE SET NULL

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("users_referred_by_fkey", "users", type_="foreignkey")
    op.create_foreign_key(
        "users_referred_by_fkey",
        "users",
        "users",
        ["referred_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("users_referred_by_fkey", "users", type_="foreignkey")
    op.create_foreign_key(
        "users_referred_by_fkey",
        "users",
        "users",
        ["referred_by"],
        ["id"],
    )
