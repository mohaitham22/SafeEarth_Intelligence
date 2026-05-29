import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from database import Base
from models.enums import DataQuality, SeverityLevel

if TYPE_CHECKING:
    from models.user import User


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # nullable — guest predictions are not persisted; authenticated ones have a user_id
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    region_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    disaster_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    probability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    severity_level: Mapped[Optional[SeverityLevel]] = mapped_column(
        SAEnum(SeverityLevel, name="severitylevel",
               values_callable=lambda obj: [e.value for e in obj]),
        nullable=True,
    )
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_deaths: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_injuries: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_affected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_damage_usd: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    uninsured_loss_usd: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    shap_explanation: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    secondary_disaster_warning: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    seasonal_peak_months: Mapped[Optional[List[int]]] = mapped_column(
        ARRAY(Integer), nullable=True
    )
    data_quality: Mapped[Optional[DataQuality]] = mapped_column(
        SAEnum(DataQuality, name="dataquality"), nullable=True
    )
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # forecast_batch_id groups all 30 rows of a 30-day forecast run
    forecast_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # 0–29 for forecast rows; null for single predictions
    forecast_day_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="predictions")
