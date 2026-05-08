"""Database package for Lean Agent Orchestrator."""

import asyncio

from asyncpg import Pool
from asyncpg import create_pool as asyncpg_create_pool

from src.db.schema import close_dao, get_dao, init_db
from src.db.schema import create_pool as schema_create_pool

# Global pool instance (lazy-loaded)
_pool: Pool | None = None


async def create_pool(database_url: str) -> Pool:
    """
    Create a new connection pool.

    Args:
        database_url: PostgreSQL connection string

    Returns:
        asyncpg Pool instance
    """
    return await asyncpg_create_pool(
        database_url,
        min_size=1,
        max_size=10,
        command_timeout=60,
    )


async def get_pool() -> Pool:
    """
    Get the global connection pool.

    Returns:
        The cached asyncpg Pool instance

    Raises:
        RuntimeError: If pool is not initialized
    """
    global _pool

    if _pool is None:
        from src.config import settings

        _pool = await create_pool(settings.database_url)

    return _pool


async def init_db(pool: Pool) -> None:
    """
    Initialize the database schema.

    Args:
        pool: asyncpg connection pool
    """
    await schema_create_pool(pool)


async def close_pool() -> None:
    """Close the global connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


__all__ = ["init_db", "create_pool", "get_pool", "close_pool", "get_dao", "close_dao"]
