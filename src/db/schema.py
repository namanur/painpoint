"""
Database schema and connection management for Multi-DB Support (PostgreSQL & SQLite)
"""

import logging
import os
from typing import Any, Dict, List, Optional, Union

import aiosqlite
import asyncpg

from src.config import settings

logger = logging.getLogger(__name__)

# Generalized Schema (PostgreSQL & SQLite compatible)
SCHEMA_SQL = """
-- Workflows table
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'DRAFT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Nodes table
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    prompt_contract TEXT NOT NULL, -- JSON stored as TEXT in SQLite, JSONB in PG
    output TEXT,
    status TEXT DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Edges table
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(id) ON DELETE CASCADE,
    from_node_id TEXT REFERENCES nodes(id),
    to_node_id TEXT REFERENCES nodes(id),
    condition_rule TEXT -- JSON stored as TEXT
);

-- Execution logs
CREATE TABLE IF NOT EXISTS execution_logs (
    id TEXT PRIMARY KEY,
    node_id TEXT REFERENCES nodes(id) ON DELETE CASCADE,
    workflow_id TEXT REFERENCES workflows(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """Unified Database Interface for PostgreSQL and SQLite."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.is_sqlite = dsn.startswith("sqlite")
        self.pool: Optional[asyncpg.Pool] = None
        self._sqlite_conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Establish connection or pool."""
        if self.is_sqlite:
            db_path = self.dsn.replace("sqlite:///", "")
            # Ensure directory exists for sqlite file
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self._sqlite_conn = await aiosqlite.connect(db_path)
            # Enable foreign keys for SQLite
            await self._sqlite_conn.execute("PRAGMA foreign_keys = ON")
        else:
            self.pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=settings.pool_min_size,
                max_size=settings.pool_max_size,
            )

    async def disconnect(self):
        """Close connection or pool."""
        if self.is_sqlite and self._sqlite_conn:
            await self._sqlite_conn.close()
        elif self.pool:
            await self.pool.close()

    async def execute(self, query: str, *args):
        """Execute a write query."""
        if self.is_sqlite:
            # SQLite uses ? for placeholders instead of $1, $2
            sqlite_query = self._convert_placeholders(query)
            await self._sqlite_conn.execute(sqlite_query, args)
            await self._sqlite_conn.commit()
        else:
            async with self.pool.acquire() as conn:
                await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetch multiple rows."""
        if self.is_sqlite:
            sqlite_query = self._convert_placeholders(query)
            self._sqlite_conn.row_factory = aiosqlite.Row
            async with self._sqlite_conn.execute(sqlite_query, args) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        else:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(row) for row in rows]

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value."""
        if self.is_sqlite:
            sqlite_query = self._convert_placeholders(query)
            async with self._sqlite_conn.execute(sqlite_query, args) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        else:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(query, *args)

    def _convert_placeholders(self, query: str) -> str:
        """Convert $1, $2 style placeholders to ? for SQLite."""
        import re

        return re.sub(r"\$\d+", "?", query)

    async def init_schema(self):
        """Initialize schema tables."""
        if self.is_sqlite:
            # SQLite doesn't support multiple statements in execute() easily
            # Split by semicolon but handle potential ones in strings (simplified here)
            for statement in SCHEMA_SQL.split(";"):
                if statement.strip():
                    await self.execute(statement)
        else:
            await self.execute(SCHEMA_SQL)


# Global database instance
db = Database(settings.database_url)


async def init_db(pool=None) -> None:
    """Wrapper for legacy calls to init_db."""
    await db.connect()
    await db.init_schema()


async def create_pool(dsn: str, **kwargs) -> Database:
    """Wrapper for legacy calls to create_pool."""
    new_db = Database(dsn)
    await new_db.connect()
    return new_db
