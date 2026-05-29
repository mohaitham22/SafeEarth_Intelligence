"""add_unsubscribe_token_to_subscriptions

Revision ID: 45befcdf72a9
Revises: a3f1d2e4b5c6
Create Date: 2026-05-25 11:36:08.380000

"""
import secrets

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '45befcdf72a9'
down_revision = 'a3f1d2e4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add column NULLABLE first so Postgres accepts it on a non-empty table.
    op.add_column(
        "subscriptions",
        sa.Column("unsubscribe_token", sa.String(255), nullable=True),
    )

    # 2. Backfill any existing rows with unique tokens before enforcing constraints.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM subscriptions WHERE unsubscribe_token IS NULL")
    ).fetchall()
    for row in rows:
        conn.execute(
            sa.text(
                "UPDATE subscriptions SET unsubscribe_token = :token WHERE id = :id"
            ),
            {"token": secrets.token_urlsafe(32), "id": str(row[0])},
        )

    # 3. Now add UNIQUE + NOT NULL after the backfill succeeds.
    op.alter_column("subscriptions", "unsubscribe_token", nullable=False)
    op.create_unique_constraint(
        "uq_subscriptions_unsubscribe_token", "subscriptions", ["unsubscribe_token"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_subscriptions_unsubscribe_token", "subscriptions", type_="unique"
    )
    op.drop_column("subscriptions", "unsubscribe_token")
