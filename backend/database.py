import re
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings


def _prepare_db_url(url: str) -> tuple[str, dict]:
    """asyncpg doesn't accept sslmode/channel_binding as URL params — strip them
    and pass ssl=True via connect_args instead."""
    needs_ssl = "sslmode=require" in url or "neon.tech" in url
    clean = re.sub(r"[?&]sslmode=[^&]*", "", url)
    clean = re.sub(r"[?&]channel_binding=[^&]*", "", clean)
    clean = re.sub(r"\?$", "", clean)  # remove trailing bare ?
    connect_args = {"ssl": True} if needs_ssl else {}
    return clean, connect_args


_db_url, _connect_args = _prepare_db_url(get_settings().database_url)

engine = create_async_engine(
    _db_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
