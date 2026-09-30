from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BusinessHour(Base):
    __tablename__ = "business_hours"
    __table_args__ = (
        UniqueConstraint("day_of_week", name="uq_business_hours_day_of_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    day_of_week: Mapped[int] = mapped_column(nullable=False, index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opening_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    closing_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
