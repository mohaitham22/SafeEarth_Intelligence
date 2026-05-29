import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from database import Base
from models.enums import RecommendationCategory, SeverityLevel


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    disaster_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity_level: Mapped[SeverityLevel] = mapped_column(
        SAEnum(SeverityLevel, name="severitylevel",
               values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[RecommendationCategory]] = mapped_column(
        SAEnum(RecommendationCategory, name="recommendationcategory"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
