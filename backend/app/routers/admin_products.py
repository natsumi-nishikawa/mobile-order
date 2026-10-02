from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category import Category
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.models.selection import Selection
from app.schemas.admin_product import (
    AdminCategoryResponse,
    AdminProductResponse,
    AdminProductWrite,
)
from app.services.product_images import (
    create_image_url,
    delete_product_image,
    upload_product_image,
)


router = APIRouter(prefix="/api/admin", tags=["Admin products"])


def validate_product(data: AdminProductWrite, db: Session) -> tuple[str, list[Category]]:
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="商品名を入力してください")

    category_ids = list(dict.fromkeys(data.category_ids))
    categories = db.scalars(
        select(Category).where(Category.id.in_(category_ids))
    ).all()
    if len(categories) != len(category_ids):
        raise HTTPException(status_code=422, detail="存在しないカテゴリが含まれています")
    return name, list(categories)


def product_response(product: Product, db: Session) -> AdminProductResponse:
    categories = db.execute(
        select(Category)
        .join(ProductCategory, ProductCategory.category_id == Category.id)
        .where(ProductCategory.product_id == product.id)
        .order_by(Category.display_order, Category.id)
    ).scalars().all()
    return AdminProductResponse(
        id=product.id,
        name=product.name,
        price=product.price,
        description=product.description,
        image_url=create_image_url(product.image_url),
        is_sold_out=product.is_sold_out,
        display_order=product.display_order,
        category_ids=[category.id for category in categories],
        category_names=[category.name for category in categories],
    )


def image_is_used_by_another_product(
    object_key: str | None,
    product_id: int,
    db: Session,
) -> bool:
    if not object_key:
        return False
    return db.scalar(
        select(Product.id).where(
            Product.image_url == object_key,
            Product.id != product_id,
        ).limit(1)
    ) is not None


@router.get("/categories", response_model=list[AdminCategoryResponse])
def get_admin_categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.display_order, Category.id)).all()


@router.get("/products", response_model=list[AdminProductResponse])
def get_admin_products(db: Session = Depends(get_db)):
    products = db.scalars(
        select(Product).order_by(Product.display_order.nullslast(), Product.id)
    ).all()
    return [product_response(product, db) for product in products]


@router.post(
    "/products",
    response_model=AdminProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_product(data: AdminProductWrite, db: Session = Depends(get_db)):
    name, categories = validate_product(data, db)
    product = Product(
        name=name,
        price=data.price,
        description=data.description.strip() or None if data.description else None,
        image_url=None,
        is_sold_out=data.is_sold_out,
        display_order=data.display_order,
    )
    db.add(product)
    db.flush()
    db.add_all([
        ProductCategory(product_id=product.id, category_id=category.id)
        for category in categories
    ])
    db.commit()
    db.refresh(product)
    return product_response(product, db)


@router.get("/products/{product_id}", response_model=AdminProductResponse)
def get_admin_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    return product_response(product, db)


@router.put("/products/{product_id}", response_model=AdminProductResponse)
def update_admin_product(
    product_id: int,
    data: AdminProductWrite,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    name, categories = validate_product(data, db)
    product.name = name
    product.price = data.price
    product.description = data.description.strip() or None if data.description else None
    product.is_sold_out = data.is_sold_out
    product.display_order = data.display_order
    db.execute(delete(ProductCategory).where(ProductCategory.product_id == product.id))
    db.add_all([
        ProductCategory(product_id=product.id, category_id=category.id)
        for category in categories
    ])
    db.commit()
    db.refresh(product)
    return product_response(product, db)


@router.post("/products/{product_id}/image", response_model=AdminProductResponse)
async def replace_admin_product_image(
    product_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    old_object_key = product.image_url
    new_object_key = await upload_product_image(image)
    product.image_url = new_object_key
    try:
        db.commit()
        db.refresh(product)
    except Exception:
        db.rollback()
        delete_product_image(new_object_key)
        raise

    if (
        old_object_key
        and old_object_key != new_object_key
        and not image_is_used_by_another_product(old_object_key, product.id, db)
    ):
        delete_product_image(old_object_key)
    return product_response(product, db)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    is_used = (
        db.scalar(select(OrderItem.id).where(OrderItem.product_id == product_id).limit(1))
        is not None
        or db.scalar(select(Selection.id).where(Selection.product_id == product_id).limit(1))
        is not None
    )
    if is_used:
        raise HTTPException(
            status_code=409,
            detail="注文履歴または選択中データがあるため削除できません",
        )

    object_key = product.image_url
    db.execute(delete(ProductCategory).where(ProductCategory.product_id == product_id))
    db.delete(product)
    db.commit()
    if not image_is_used_by_another_product(object_key, product_id, db):
        delete_product_image(object_key)
