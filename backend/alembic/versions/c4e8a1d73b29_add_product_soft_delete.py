"""add product soft delete

Revision ID: c4e8a1d73b29
Revises: 9b1d72f4a6c3
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e8a1d73b29"
down_revision: Union[str, Sequence[str], None] = "9b1d72f4a6c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("products", "is_deleted")
