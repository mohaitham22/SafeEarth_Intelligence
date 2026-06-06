"""add ads table (home-page promotional content, Studio-managed in Phase 10)

Revision ID: b7c1e9d4a2f0
Revises: 45befcdf72a9
Create Date: 2026-06-03 20:30:00.000000
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7c1e9d4a2f0"
down_revision = "45befcdf72a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("link_url", sa.String(1000), nullable=True),
        sa.Column("cta_label", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
    )

    # Seed placeholder ads so guests see content before the Studio editor exists.
    ads_table = sa.table(
        "ads",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("title", sa.String),
        sa.column("body", sa.Text),
        sa.column("image_url", sa.String),
        sa.column("link_url", sa.String),
        sa.column("cta_label", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        ads_table,
        [
            {
                "id": uuid.uuid4(),
                "title": "Unlock the 30-day forecast",
                "body": "Go Premium to see a day-by-day disaster risk forecast for every region you follow.",
                "image_url": None,
                "link_url": "/pricing",
                "cta_label": "See plans",
                "is_active": True,
                "sort_order": 0,
            },
            {
                "id": uuid.uuid4(),
                "title": "Explore the global risk map",
                "body": "Browse 120 years of disaster history across every continent on the interactive heatmap.",
                "image_url": None,
                "link_url": "/map",
                "cta_label": "Open the map",
                "is_active": True,
                "sort_order": 1,
            },
            {
                "id": uuid.uuid4(),
                "title": "Create a free account",
                "body": "Run predictions, subscribe to region alerts, and track your history — free, forever.",
                "image_url": None,
                "link_url": "/register",
                "cta_label": "Sign up",
                "is_active": True,
                "sort_order": 2,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("ads")
