"""initial schema

Revision ID: a3f1d2e4b5c6
Revises:
Create Date: 2026-05-18 00:00:00.000000
"""

from decimal import Decimal
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3f1d2e4b5c6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── PostgreSQL ENUM types ─────────────────────────────────────────────────
    # Created once here; all op.create_table() calls reference them with create_type=False.
    op.execute("CREATE TYPE userrole AS ENUM ('guest', 'subscriber', 'premium', 'admin')")
    op.execute("CREATE TYPE alertfrequency AS ENUM ('weekly', 'immediate')")
    op.execute("CREATE TYPE severitylevel AS ENUM ('Low', 'Medium', 'High', 'Critical')")
    op.execute("CREATE TYPE dataquality AS ENUM ('full', 'limited')")
    op.execute("CREATE TYPE alerttype AS ENUM ('weekly_digest', 'high_risk_immediate')")
    op.execute("CREATE TYPE alertstatus AS ENUM ('sent', 'failed', 'pending')")
    op.execute("CREATE TYPE recommendationcategory AS ENUM ('evacuation', 'kit', 'shelter', 'medical', 'contact')")
    op.execute("CREATE TYPE paymentstatus AS ENUM ('pending', 'succeeded', 'failed', 'refunded')")
    op.execute("CREATE TYPE emailtype AS ENUM ('immediate_high_risk', 'weekly_digest_premium', 'custom')")
    op.execute("CREATE TYPE emailstatus AS ENUM ('sent', 'failed', 'bounced')")

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column(
            "role",
            postgresql.ENUM(name="userrole", create_type=False),
            nullable=False,
            server_default="subscriber",
        ),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("verification_token", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email"),
    )

    # ── premium_plans ─────────────────────────────────────────────────────────
    op.create_table(
        "premium_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("price_usd", sa.Numeric(8, 2), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("max_subscriptions", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.UniqueConstraint("name"),
    )

    # ── subscriptions ─────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("region_name", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "alert_frequency",
            postgresql.ENUM(name="alertfrequency", create_type=False),
            nullable=False,
            server_default="weekly",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # ── predictions ───────────────────────────────────────────────────────────
    op.create_table(
        "predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("region_name", sa.String(255), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("disaster_type", sa.String(100), nullable=True),
        sa.Column("probability_score", sa.Float(), nullable=True),
        sa.Column(
            "severity_level",
            postgresql.ENUM(name="severitylevel", create_type=False),
            nullable=True,
        ),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("estimated_deaths", sa.Integer(), nullable=True),
        sa.Column("estimated_injuries", sa.Integer(), nullable=True),
        sa.Column("estimated_affected", sa.Integer(), nullable=True),
        sa.Column("estimated_damage_usd", sa.BigInteger(), nullable=True),
        sa.Column("uninsured_loss_usd", sa.BigInteger(), nullable=True),
        sa.Column("shap_explanation", postgresql.JSONB(), nullable=True),
        sa.Column("secondary_disaster_warning", sa.String(500), nullable=True),
        sa.Column(
            "seasonal_peak_months",
            postgresql.ARRAY(sa.Integer()),
            nullable=True,
        ),
        sa.Column(
            "data_quality",
            postgresql.ENUM(name="dataquality", create_type=False),
            nullable=True,
        ),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("forecast_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("forecast_day_offset", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # ── recommendations ───────────────────────────────────────────────────────
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("disaster_type", sa.String(100), nullable=False),
        sa.Column(
            "severity_level",
            postgresql.ENUM(name="severitylevel", create_type=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "category",
            postgresql.ENUM(name="recommendationcategory", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ── alerts ────────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "alert_type",
            postgresql.ENUM(name="alerttype", create_type=False),
            nullable=False,
        ),
        sa.Column("disaster_type", sa.String(100), nullable=True),
        sa.Column(
            "severity_level",
            postgresql.ENUM(name="severitylevel", create_type=False),
            nullable=True,
        ),
        sa.Column("message_body", sa.Text(), nullable=True),
        sa.Column("sent_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="alertstatus", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # ── payments ──────────────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_transaction_id", sa.String(255), nullable=True),
        sa.Column("amount_usd", sa.Numeric(8, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column(
            "status",
            postgresql.ENUM(name="paymentstatus", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("premium_activated_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("premium_expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["premium_plans.id"], ondelete="RESTRICT"),
    )

    # ── premium_email_logs ────────────────────────────────────────────────────
    op.create_table(
        "premium_email_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resend_message_id", sa.String(255), nullable=True),
        sa.Column(
            "email_type",
            postgresql.ENUM(name="emailtype", create_type=False),
            nullable=False,
        ),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="emailstatus", create_type=False),
            nullable=False,
            server_default="sent",
        ),
        sa.Column(
            "sent_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="SET NULL"),
    )

    # ── Seed premium_plans ────────────────────────────────────────────────────
    premium_plans_table = sa.table(
        "premium_plans",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String(50)),
        sa.column("price_usd", sa.Numeric(8, 2)),
        sa.column("duration_days", sa.Integer()),
        sa.column("max_subscriptions", sa.Integer()),
        sa.column("description", sa.Text()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        premium_plans_table,
        [
            {
                "id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
                "name": "monthly",
                "price_usd": Decimal("5.00"),
                "duration_days": 30,
                "max_subscriptions": 10,
                "description": "SafeEarth Premium Monthly Plan",
                "is_active": True,
            },
            {
                "id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
                "name": "yearly",
                "price_usd": Decimal("48.00"),
                "duration_days": 365,
                "max_subscriptions": 10,
                "description": "SafeEarth Premium Yearly Plan (Save 20%)",
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    # Drop tables in reverse FK dependency order
    op.drop_table("premium_email_logs")
    op.drop_table("payments")
    op.drop_table("alerts")
    op.drop_table("recommendations")
    op.drop_table("predictions")
    op.drop_table("subscriptions")
    op.drop_table("premium_plans")
    op.drop_table("users")

    # Drop ENUM types (must come after all tables that reference them are gone)
    op.execute("DROP TYPE IF EXISTS emailstatus")
    op.execute("DROP TYPE IF EXISTS emailtype")
    op.execute("DROP TYPE IF EXISTS paymentstatus")
    op.execute("DROP TYPE IF EXISTS recommendationcategory")
    op.execute("DROP TYPE IF EXISTS alertstatus")
    op.execute("DROP TYPE IF EXISTS alerttype")
    op.execute("DROP TYPE IF EXISTS dataquality")
    op.execute("DROP TYPE IF EXISTS severitylevel")
    op.execute("DROP TYPE IF EXISTS alertfrequency")
    op.execute("DROP TYPE IF EXISTS userrole")
