"""
Seed test accounts for all roles directly into the DB (bypasses email verification).

Usage:
  Set DATABASE_URL to your Neon connection string, then run:
  DATABASE_URL="postgresql+asyncpg://..." py -3.12 scripts/seed_test_users.py

  Or on Windows PowerShell:
  $env:DATABASE_URL="postgresql+asyncpg://..."; py -3.12 scripts/seed_test_users.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "backend")

# Override DATABASE_URL before importing config
db_url = os.environ.get("DATABASE_URL")
if db_url:
    os.environ["DATABASE_URL"] = db_url

from sqlalchemy import select
from database import AsyncSessionLocal
from models.user import User
from models.enums import UserRole
from core.security import hash_password
from datetime import datetime, timezone, timedelta

TEST_USERS = [
    {
        "email": "subscriber@safeearth.test",
        "password": "SafeEarth2026!",
        "full_name": "Test Subscriber",
        "role": UserRole.subscriber,
        "premium_expires_at": None,
    },
    {
        "email": "premium@safeearth.test",
        "password": "SafeEarth2026!",
        "full_name": "Test Premium",
        "role": UserRole.premium,
        "premium_expires_at": datetime.now(timezone.utc) + timedelta(days=365),
    },
    {
        "email": "admin@safeearth.test",
        "password": "SafeEarth2026!",
        "full_name": "Test Admin",
        "role": UserRole.admin,
        "premium_expires_at": None,
    },
]


async def seed():
    inserted = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        for u in TEST_USERS:
            existing = await db.execute(select(User).where(User.email == u["email"]))
            if existing.scalar_one_or_none():
                print(f"  skip  {u['email']} (already exists)")
                skipped += 1
                continue

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

        await db.commit()

    print(f"\nDone. {inserted} inserted, {skipped} skipped.")
    print("\n─── Test credentials ───────────────────────────────")
    print(f"  {'Role':<12} {'Email':<30} {'Password'}")
    print(f"  {'────':<12} {'─────':<30} {'────────'}")
    for u in TEST_USERS:
        print(f"  {u['role'].value:<12} {u['email']:<30} {u['password']}")
    print("────────────────────────────────────────────────────")


if __name__ == "__main__":
    asyncio.run(seed())
