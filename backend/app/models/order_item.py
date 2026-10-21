from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(
            "quantity >= 1 AND quantity <= 50",
            name="ck_order_items_quantity_range",
        ),
        CheckConstraint(
            "canceled_quantity >= 0 AND canceled_quantity <= quantity",
            name="ck_order_items_canceled_quantity_range",
        ),
        CheckConstraint(
            "served_quantity >= 0 AND served_quantity <= quantity",
            name="ck_order_items_served_quantity_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    unit_price: Mapped[int] = mapped_column(nullable=False)
    canceled_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    served_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
