import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.payment import Payment


class PremiumPlan(Base):
    __tablename__ = "premium_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_subscriptions: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="plan")
