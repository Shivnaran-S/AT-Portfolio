"""
Async SQLAlchemy database engine and session management.

Uses asyncpg as the PostgreSQL driver for non-blocking database access.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Create the async engine. pool_pre_ping ensures stale connections are detected.
engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

# Session factory — expire_on_commit=False prevents lazy-load errors after commit.
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def get_db():
    """
    FastAPI dependency that provides a database session.

    Usage in a router:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...

    The session is automatically closed when the request finishes.
    """
    async with async_session() as session:
        yield session
