import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from database import Base
from models.enums import AlertStatus, AlertType, SeverityLevel

if TYPE_CHECKING:
    from models.premium_email_log import PremiumEmailLog
    from models.subscription import Subscription
    from models.user import User


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    alert_type: Mapped[AlertType] = mapped_column(
        SAEnum(AlertType, name="alerttype"), nullable=False
    )
    disaster_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    severity_level: Mapped[Optional[SeverityLevel]] = mapped_column(
        SAEnum(SeverityLevel, name="severitylevel",
               values_callable=lambda obj: [e.value for e in obj]),
        nullable=True,
    )
    message_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(AlertStatus, name="alertstatus"),
        nullable=False,
        default=AlertStatus.pending,
    )

    subscription: Mapped["Subscription"] = relationship(
        "Subscription", back_populates="alerts"
    )
    user: Mapped["User"] = relationship("User", back_populates="alerts")
    premium_email_logs: Mapped[List["PremiumEmailLog"]] = relationship(
        "PremiumEmailLog", back_populates="alert"
    )
