import asyncio
import re
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Add backend/ to sys.path so bare imports (from config import ..., from database import ...)
# work regardless of the working directory Alembic is invoked from.
_backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from config import get_settings  # noqa: E402
from database import Base  # noqa: E402
import models  # noqa: E402, F401 — registers all 8 ORM models with Base.metadata

config = context.config


def _clean_db_url(url: str) -> tuple[str, dict]:
    """Strip asyncpg-incompatible URL params; return (clean_url, connect_args)."""
    needs_ssl = "sslmode=require" in url or "neon.tech" in url
    clean = re.sub(r"[?&]sslmode=[^&]*", "", url)
    clean = re.sub(r"[?&]channel_binding=[^&]*", "", clean)
    clean = re.sub(r"\?$", "", clean)
    return clean, ({"ssl": True} if needs_ssl else {})


_raw_url = get_settings().database_url
_db_url, _connect_args = _clean_db_url(_raw_url)

# Set cleaned URL so offline mode and logging still work.
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        _db_url,
        poolclass=pool.NullPool,
        connect_args=_connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
