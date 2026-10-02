from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.customer_auth import CurrentCustomer, get_current_customer
from app.models.category import Category
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.schemas.customer import CategoryResponse, ProductResponse


router = APIRouter(
    prefix="/api/customer",
    tags=["Customer"],
)


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
)
def get_categories(
    db: Session = Depends(get_db),
    _customer: CurrentCustomer = Depends(get_current_customer),
):
    categories = db.scalars(
        select(Category).order_by(Category.display_order)
    ).all()

    return categories


@router.get(
    "/products",
    response_model=list[ProductResponse],
)
def get_products(
    db: Session = Depends(get_db),
    _customer: CurrentCustomer = Depends(get_current_customer),
):
    products = db.scalars(
        select(Product).order_by(
            Product.display_order,
            Product.id,
        )
    ).all()

    result = []

    for product in products:
        category_ids = db.scalars(
            select(ProductCategory.category_id).where(
                ProductCategory.product_id == product.id
            )
        ).all()

        result.append(
            ProductResponse(
                id=product.id,
                name=product.name,
                price=product.price,
                description=product.description,
                image_url=product.image_url,
                is_sold_out=product.is_sold_out,
                display_order=product.display_order,
                category_ids=list(category_ids),
            )
        )

    return result
