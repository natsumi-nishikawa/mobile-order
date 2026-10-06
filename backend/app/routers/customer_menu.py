from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.customer_auth import CurrentCustomer, get_current_customer
from app.schemas.customer import CategoryResponse, ProductResponse
from app.services.menu_catalog import get_menu_categories, get_menu_products
from app.services.product_images import create_image_url


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
    return get_menu_categories(db)


@router.get(
    "/products",
    response_model=list[ProductResponse],
)
def get_products(
    db: Session = Depends(get_db),
    _customer: CurrentCustomer = Depends(get_current_customer),
):
    result = []
    for product, category_ids in get_menu_products(db):
        result.append(
            ProductResponse(
                id=product.id,
                name=product.name,
                price=product.price,
                description=product.description,
                image_url=create_image_url(product.image_url),
                is_sold_out=product.is_sold_out,
                display_order=product.display_order,
                category_ids=category_ids,
            )
        )

    return result
