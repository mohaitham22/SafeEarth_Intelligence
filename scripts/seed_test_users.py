"""
Seed test accounts for all roles directly into the DB (bypasses email verification).

The premium account gets a real payments row (status=succeeded, expires 2099-12-31)
so the daily expiry checker never downgrades it.

Usage:
  py -3.12 scripts/seed_test_users.py

  Against Neon (production):
  $env:DATABASE_URL="postgresql+asyncpg://..."; py -3.12 scripts/seed_test_users.py
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, "backend")

db_url = os.environ.get("DATABASE_URL")
if db_url:
    os.environ["DATABASE_URL"] = db_url

from sqlalchemy import select
from database import AsyncSessionLocal
from models.user import User
from models.payment import Payment
from models.premium_plan import PremiumPlan
from models.enums import UserRole, PaymentStatus
from core.security import hash_password

_NEVER_EXPIRES = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

TEST_USERS = [
    {
        "email": "subscriber@safeearth.dev",
        "password": "SafeEarth2026!",
        "full_name": "Test Subscriber",
        "role": UserRole.subscriber,
        "seed_payment": False,
    },
    {
        "email": "premium@safeearth.dev",
        "password": "SafeEarth2026!",
        "full_name": "Test Premium",
        "role": UserRole.premium,
        "seed_payment": True,   # payment row keeps role=premium forever
    },
    {
        "email": "admin@safeearth.dev",
        "password": "SafeEarth2026!",
        "full_name": "Test Admin",
        "role": UserRole.admin,
        "seed_payment": False,
    },
]


async def seed():
    inserted = 0
    skipped = 0
    payments_added = 0

    async with AsyncSessionLocal() as db:
        # Fetch the "yearly" plan to attach to the premium payment row.
        result = await db.execute(
            select(PremiumPlan).where(PremiumPlan.name == "yearly")
        )
        yearly_plan = result.scalar_one_or_none()
        if yearly_plan is None:
            print("ERROR: 'yearly' premium plan not found in DB.")
            print("Run: alembic upgrade head  (the initial migration seeds premium_plans)")
            return

        for u in TEST_USERS:
            result = await db.execute(select(User).where(User.email == u["email"]))
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    email=u["email"],
                    password_hash=hash_password(u["password"]),
                    full_name=u["full_name"],
                    role=u["role"],
                    is_verified=True,
                    verification_token=None,
                )
                db.add(user)
                await db.flush()
                print(f"  added {u['email']}  role={u['role'].value}")
                inserted += 1
            else:
                # Ensure role is correct even if account existed with wrong role.
                if user.role != u["role"]:
                    user.role = u["role"]
                    print(f"  fixed {u['email']}  role -> {u['role'].value}")
                else:
                    print(f"  skip  {u['email']} (already exists)")
                skipped += 1

            # Seed a permanent payment record for the premium account so the
            # daily expiry checker (downgrade_expired_premium) never touches it.
            if u["seed_payment"]:
                result = await db.execute(
                    select(Payment).where(
                        Payment.user_id == user.id,
                        Payment.status == PaymentStatus.succeeded,
                    )
                )
                existing_payment = result.scalar_one_or_none()

                if existing_payment is None:
                    payment = Payment(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        plan_id=yearly_plan.id,
                        provider="seed",
                        provider_transaction_id=f"seed_{user.id.hex[:12]}",
                        amount_usd=Decimal("0.00"),
                        currency="USD",
                        status=PaymentStatus.succeeded,
                        premium_activated_at=datetime.now(timezone.utc),
                        premium_expires_at=_NEVER_EXPIRES,
                    )
                    db.add(payment)
                    print(f"  payment added for {u['email']}  expires=2099-12-31")
                    payments_added += 1
                else:
                    # Extend expiry if it was set to something short.
                    if (
                        existing_payment.premium_expires_at is None
                        or existing_payment.premium_expires_at < _NEVER_EXPIRES
                    ):
                        existing_payment.premium_expires_at = _NEVER_EXPIRES
                        print(f"  payment updated for {u['email']}  expires=2099-12-31")
                        payments_added += 1
                    else:
                        print(f"  payment ok for {u['email']}")

        await db.commit()

    print(f"\nDone. {inserted} inserted, {skipped} skipped, {payments_added} payments upserted.")
    print()
    print(f"  {'Role':<12} {'Email':<30} {'Password'}")
    print(f"  {'':<12} {'-'*30} {'-'*14}")
    for u in TEST_USERS:
        print(f"  {u['role'].value:<12} {u['email']:<30} {u['password']}")


if __name__ == "__main__":
    asyncio.run(seed())
