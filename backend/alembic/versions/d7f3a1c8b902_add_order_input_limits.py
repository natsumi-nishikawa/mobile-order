"""add order and input limit checks

Revision ID: d7f3a1c8b902
Revises: c4e8a1d73b29
Create Date: 2026-10-21
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d7f3a1c8b902"
down_revision: Union[str, Sequence[str], None] = "c4e8a1d73b29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_selections_quantity_range",
        "selections",
        "quantity >= 1 AND quantity <= 20",
    )
    op.create_check_constraint(
        "ck_order_items_quantity_range",
        "order_items",
        "quantity >= 1 AND quantity <= 50",
    )
    op.create_check_constraint(
        "ck_order_items_canceled_quantity_range",
        "order_items",
        "canceled_quantity >= 0 AND canceled_quantity <= quantity",
    )
    op.create_check_constraint(
        "ck_order_items_served_quantity_range",
        "order_items",
        "served_quantity >= 0 AND served_quantity <= quantity",
    )
    op.create_check_constraint(
        "ck_products_price_range",
        "products",
        "price >= 0 AND price <= 1000000",
    )
    op.create_check_constraint(
        "ck_products_description_length",
        "products",
        "description IS NULL OR char_length(description) <= 2000",
    )
    op.create_check_constraint(
        "ck_products_display_order_range",
        "products",
        "display_order IS NULL OR (display_order >= 0 AND display_order <= 1000000)",
    )
    op.create_check_constraint(
        "ck_categories_display_order_range",
        "categories",
        "display_order >= 0 AND display_order <= 1000000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_categories_display_order_range", "categories", type_="check")
    op.drop_constraint("ck_products_display_order_range", "products", type_="check")
    op.drop_constraint("ck_products_description_length", "products", type_="check")
    op.drop_constraint("ck_products_price_range", "products", type_="check")
    op.drop_constraint("ck_order_items_served_quantity_range", "order_items", type_="check")
    op.drop_constraint("ck_order_items_canceled_quantity_range", "order_items", type_="check")
    op.drop_constraint("ck_order_items_quantity_range", "order_items", type_="check")
    op.drop_constraint("ck_selections_quantity_range", "selections", type_="check")
