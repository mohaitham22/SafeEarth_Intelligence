import enum


class UserRole(str, enum.Enum):
    guest = "guest"
    subscriber = "subscriber"
    premium = "premium"
    admin = "admin"


class AlertFrequency(str, enum.Enum):
    weekly = "weekly"
    immediate = "immediate"


class SeverityLevel(str, enum.Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    critical = "Critical"


class DataQuality(str, enum.Enum):
    full = "full"
    limited = "limited"


class AlertType(str, enum.Enum):
    weekly_digest = "weekly_digest"
    high_risk_immediate = "high_risk_immediate"


class AlertStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"
    pending = "pending"


class RecommendationCategory(str, enum.Enum):
    evacuation = "evacuation"
    kit = "kit"
    shelter = "shelter"
    medical = "medical"
    contact = "contact"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class EmailType(str, enum.Enum):
    immediate_high_risk = "immediate_high_risk"
    weekly_digest_premium = "weekly_digest_premium"
    custom = "custom"


class EmailStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"
    bounced = "bounced"
