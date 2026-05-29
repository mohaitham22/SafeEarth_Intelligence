# SKILL: Add a New Database Table

Read this file completely before creating any SQLAlchemy model or Alembic migration.
This is the binding pattern for every table in SafeEarth Intelligence.

---

## The 3-Step Rule

1. Define the SQLAlchemy model in `backend/models/{table}.py`
2. Import the model in `backend/models/__init__.py` (so Alembic sees it)
3. Generate and apply the Alembic migration

Never skip the migration. Never ALTER TABLE directly in psql or Neon.
Never write raw SQL CREATE TABLE statements.

---

## Step 1 — SQLAlchemy Model Template

Every model must follow this exact structure.

```python
# backend/models/prediction.py
from sqlalchemy import Column, String, Float, Integer, BigInteger, Boolean, Text, Enum, ARRAY, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from database import Base  # always import from here

# — Enums (define at top of file, before the model class) —
class SeverityLevel(str, enum.Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    critical = "Critical"

# — Model Class —
class Prediction(Base):
    __tablename__ = "predictions"

    # Primary key — always UUID, always this pattern
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys — always specify ondelete
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    # Standard columns
    region_name          = Column(String(255))
    latitude             = Column(Float)
    longitude            = Column(Float)
    disaster_type        = Column(String(100))
    probability_score    = Column(Float)
    severity_level       = Column(Enum(SeverityLevel))
    risk_score           = Column(Float)
    estimated_deaths     = Column(Integer)
    estimated_injuries   = Column(Integer)
    estimated_affected   = Column(Integer)
    estimated_damage_usd = Column(BigInteger)
    uninsured_loss_usd   = Column(BigInteger)

    # JSONB column (for structured data like SHAP results)
    shap_explanation = Column(JSONB)

    # PostgreSQL array column
    seasonal_peak_months = Column(ARRAY(Integer))

    secondary_disaster_warning = Column(String(500), nullable=True)
    model_version              = Column(String(50))

    # Timestamps — always UTC, always this pattern
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="predictions")

    def __repr__(self):
        return f"<Prediction {self.id} — {self.disaster_type} {self.severity_level}>"
```

---

## Step 2 — Register in __init__.py

Every model must be imported in `backend/models/__init__.py`.
Alembic discovers models through this file via autogenerate.
If you skip this, your migration will be empty.

```python
# backend/models/__init__.py
from models.user import User
from models.subscription import Subscription
from models.prediction import Prediction
from models.alert import Alert
from models.recommendation import Recommendation
from models.premium_plan import PremiumPlan
from models.payment import Payment
from models.premium_email_log import PremiumEmailLog
# Add new models here — one line per model
```

---

## Step 3 — Generate and Apply Migration

Run these commands in order from the `backend/` directory:

```bash
# 1. Generate the migration with a descriptive name
alembic revision --autogenerate -m "add_predictions_table"

# 2. Review the generated file in alembic/versions/
# Check upgrade() has correct columns
# Check downgrade() has the correct drop_table call
# If it is empty, the model is not imported in models/__init__.py

# 3. Apply the migration
alembic upgrade head

# 4. Verify
alembic current
```

---

## Column Type Reference

```python
# Strings
Column(String(50))      # short codes, versions
Column(String(255))     # names, emails, region names
Column(String(500))     # warning messages
Column(Text)            # long text, email bodies

# Numbers
Column(Integer)         # deaths, injuries, counts
Column(BigInteger)      # damage in USD — can exceed Integer limit
Column(Float)           # probability scores, coordinates, ratios

# Boolean
Column(Boolean, default=True)

# PostgreSQL-specific (import from sqlalchemy.dialects.postgresql)
Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
Column(JSONB)                    # SHAP results, structured metadata
Column(ARRAY(Integer))           # seasonal_peak_months
Column(TIMESTAMP(timezone=True), server_default=func.now())

# Enums — always define as Python enum class first
Column(Enum(MyEnumClass))
```

---

## Foreign Key Rules

Always specify `ondelete`. Never leave it blank.

```python
# Parent deleted → delete child rows
user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))

# Parent deleted → set column to NULL
alert_id = Column(UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True)

# Parent deleted → block deletion (use for financial records)
plan_id = Column(UUID(as_uuid=True), ForeignKey("premium_plans.id", ondelete="RESTRICT"))
```

---

## Soft Delete Pattern

Never hard-delete records. Use soft delete for all user-facing data.
Exception: payments table — append-only, never delete.

```python
# Add to tables with user-deletable rows
is_active = Column(Boolean, default=True, nullable=False)

# To soft-delete in a service
subscription.is_active = False
await db.commit()

# Always filter in queries
select(Subscription).where(Subscription.is_active == True)
```

---

## Async Session Pattern

Every DB operation must use AsyncSession. Never use sync Session.

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

async def get_prediction(prediction_id: uuid.UUID, db: AsyncSession):
    result = await db.execute(
        select(Prediction).where(Prediction.id == prediction_id)
    )
    return result.scalar_one_or_none()

async def create_prediction(data: dict, db: AsyncSession):
    prediction = Prediction(**data)
    db.add(prediction)
    await db.commit()
    await db.refresh(prediction)
    return prediction
```

---

## Checklist Before Committing a New Table

- [ ] Model class defined in backend/models/{table}.py
- [ ] Model imported in backend/models/__init__.py
- [ ] All columns use correct types from the reference above
- [ ] All foreign keys have explicit ondelete behavior
- [ ] UUID primary key uses default=uuid.uuid4
- [ ] created_at uses server_default=func.now() and timezone=True
- [ ] Soft delete (is_active) added if the table has user-deletable rows
- [ ] Migration generated with descriptive name
- [ ] Migration file reviewed (not empty, correct columns)
- [ ] Migration applied: alembic upgrade head
- [ ] alembic current shows correct version
