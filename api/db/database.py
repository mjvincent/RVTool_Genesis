"""SQLAlchemy async engine and session factory."""
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Raw URL from environment — may use postgresql:// or postgresql+asyncpg://
_raw_url: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://rvtool:rvtool_password@db:5432/rvtooldb",
)

# Ensure asyncpg driver is specified for async engine
DATABASE_URL: str = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session and closes on exit."""
    async with AsyncSessionLocal() as session:
        yield session
