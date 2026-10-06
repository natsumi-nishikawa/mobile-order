from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.session import Session as SessionModel
from app.models.table import Table
from app.schemas.admin_table import AdminTableResponse, AdminTableWrite


router = APIRouter(prefix="/api/admin/tables", tags=["Admin tables"])


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="テーブル名を入力してください")
    return cleaned


@router.get("", response_model=list[AdminTableResponse])
def get_tables(db: Session = Depends(get_db)):
    return db.scalars(select(Table).order_by(Table.id)).all()


@router.post("", response_model=AdminTableResponse, status_code=status.HTTP_201_CREATED)
def create_table(data: AdminTableWrite, db: Session = Depends(get_db)):
    table = Table(table_name=_clean_name(data.table_name))
    db.add(table)
    db.commit()
    db.refresh(table)
    return table


@router.put("/{table_id}", response_model=AdminTableResponse)
def update_table(table_id: int, data: AdminTableWrite, db: Session = Depends(get_db)):
    table = db.get(Table, table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="テーブルが見つかりません")
    table.table_name = _clean_name(data.table_name)
    db.commit()
    db.refresh(table)
    return table


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(table_id: int, db: Session = Depends(get_db)):
    table = db.get(Table, table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="テーブルが見つかりません")
    if db.scalar(select(SessionModel.id).where(SessionModel.table_id == table_id).limit(1)):
        raise HTTPException(status_code=409, detail="利用履歴があるテーブルは削除できません")
    db.delete(table)
    db.commit()
