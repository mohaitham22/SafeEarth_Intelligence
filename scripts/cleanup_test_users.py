import asyncio, sys
sys.path.insert(0, "backend")
from database import AsyncSessionLocal
from sqlalchemy import text

async def run():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("DELETE FROM users WHERE email LIKE '%@safeearth.test'"))
        await db.commit()
        print(f"Deleted {result.rowcount} old .test users")

asyncio.run(run())
