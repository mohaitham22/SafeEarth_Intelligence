import sys
from pathlib import Path

# Add backend/ to sys.path so bare imports work (mirrors uvicorn's working directory)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from config import get_settings
from database import get_db
from main import app


@pytest.fixture(scope="session", autouse=True)
def load_emdat_data():
    """Load EM-DAT JSON data once per test session, mirroring what the FastAPI lifespan
    does at startup. ASGITransport does not fire ASGI lifespan events, so this fixture
    ensures module-level globals in emdat_lookup are populated before any test runs."""
    from ml import emdat_lookup
    emdat_lookup.load_all(get_settings().data_generated_dir)


@pytest.fixture(scope="session")
def load_ml_models():
    """Load ML pkl files once per test session — used only by prediction tests.
    Not autouse because loading 70MB of pkl files would slow down every test run."""
    from ml import predictor
    from pathlib import Path
    models_dir = Path(__file__).resolve().parent.parent / "saved_models"
    predictor.load_models(models_dir)


@pytest.fixture
async def db_session() -> AsyncSession:
    """
    Yields an AsyncSession that wraps the entire test in a transaction.
    The transaction is rolled back after each test — dev DB is never polluted.
    join_transaction_mode="create_savepoint" means session.commit() inside the
    test creates a savepoint (not a real commit), so the outer rollback undoes it.
    """
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
        echo=False,
    )
    connection = await engine.connect()
    trans = await connection.begin()

    session = AsyncSession(
        connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    yield session

    await session.close()
    await trans.rollback()
    await connection.close()
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """
    AsyncClient wired to the FastAPI app with get_db overridden to use
    the rollback session — so HTTP requests and direct DB queries share
    the same connection and see each other's uncommitted data.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
