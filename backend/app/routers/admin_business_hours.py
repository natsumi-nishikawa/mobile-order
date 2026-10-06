from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.business_hour import BusinessHour
from app.schemas.admin_business_hour import AdminBusinessHourResponse, AdminBusinessHourWrite


router = APIRouter(prefix="/api/admin/business-hours", tags=["Admin business hours"])


@router.get("", response_model=list[AdminBusinessHourResponse])
def get_business_hours(db: Session = Depends(get_db)):
    return db.scalars(select(BusinessHour).order_by(BusinessHour.day_of_week)).all()


@router.put("", response_model=list[AdminBusinessHourResponse])
def update_business_hours(data: list[AdminBusinessHourWrite], db: Session = Depends(get_db)):
    days = [item.day_of_week for item in data]
    if len(data) != 7 or set(days) != set(range(7)):
        raise HTTPException(status_code=422, detail="月曜日から日曜日までの7日分を指定してください")

    existing = {
        item.day_of_week: item
        for item in db.scalars(select(BusinessHour).with_for_update()).all()
    }
    for value in data:
        business_hour = existing.get(value.day_of_week)
        if business_hour is None:
            business_hour = BusinessHour(day_of_week=value.day_of_week)
            db.add(business_hour)
        business_hour.is_open = value.is_open
        business_hour.opening_time = value.opening_time if value.is_open else None
        business_hour.closing_time = value.closing_time if value.is_open else None

    db.commit()
    return db.scalars(select(BusinessHour).order_by(BusinessHour.day_of_week)).all()
