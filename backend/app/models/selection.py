from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Selection(Base):
    __tablename__ = "selections"
    __table_args__ = (
        UniqueConstraint("participant_id", "product_id", name="uq_selections_participant_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    last_selected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
