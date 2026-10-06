from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category import Category
from app.models.product_category import ProductCategory
from app.schemas.admin_category import AdminCategoryResponse, AdminCategoryWrite
from app.store_auth import require_admin


router = APIRouter(prefix="/api/admin/categories", tags=["Admin categories"], dependencies=[Depends(require_admin)])


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="カテゴリ名を入力してください")
    return cleaned


@router.post("", response_model=AdminCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(data: AdminCategoryWrite, db: Session = Depends(get_db)):
    category = Category(name=_clean_name(data.name), display_order=data.display_order)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=AdminCategoryResponse)
def update_category(category_id: int, data: AdminCategoryWrite, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="カテゴリが見つかりません")
    category.name = _clean_name(data.name)
    category.display_order = data.display_order
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="カテゴリが見つかりません")
    if db.scalar(select(ProductCategory.id).where(ProductCategory.category_id == category_id).limit(1)):
        raise HTTPException(status_code=409, detail="商品が登録されているカテゴリは削除できません")
    db.delete(category)
    db.commit()
