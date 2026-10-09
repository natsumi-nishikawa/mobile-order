from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product
from app.models.product_category import ProductCategory


def get_menu_categories(db: Session) -> list[Category]:
    return list(db.scalars(
        select(Category).order_by(Category.display_order, Category.id)
    ).all())


def get_menu_products(db: Session) -> list[tuple[Product, list[int]]]:
    products = db.scalars(
        select(Product)
        .where(Product.is_visible.is_(True), Product.is_deleted.is_(False))
        .order_by(Product.display_order, Product.id)
    ).all()
    category_rows = db.execute(
        select(ProductCategory.product_id, ProductCategory.category_id)
        .order_by(ProductCategory.id)
    ).all()
    category_ids_by_product: dict[int, list[int]] = {}
    for product_id, category_id in category_rows:
        category_ids_by_product.setdefault(product_id, []).append(category_id)
    return [(product, category_ids_by_product.get(product.id, [])) for product in products]
