"""add product visibility

Revision ID: 9b1d72f4a6c3
Revises: 14c147f1a562
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b1d72f4a6c3"
down_revision: Union[str, Sequence[str], None] = "14c147f1a562"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_visible", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("products", "is_visible")
