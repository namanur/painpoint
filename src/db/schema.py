"""
Database Abstraction Layer - Explicit DAOs for PostgreSQL and SQLite

ANTI-SLOP DIRECTIVE: Never parse SQL with regex. Never mutate query strings
at runtime. Write explicit DAOs for each database engine and inject the
correct queries at initialization.

The "unified" interface approach was a lie that would corrupt data.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import aiosqlite
import asyncpg

from src.config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# SQL STATEMENTS - Explicitly defined per database type
# =============================================================================

POSTGRES_SQL = {
    # Atomic pop: UPDATE...RETURNING with SKIP LOCKED for concurrent safety
    "fetch_pending_node": """
        UPDATE nodes
        SET status = $1
        WHERE id = (
            SELECT id FROM nodes
            WHERE status = $2
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, workflow_id, prompt_contract;
    """,
    # Standard CRUD
    "insert_node": """
        INSERT INTO nodes (id, workflow_id, type, prompt_contract, status)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id;
    """,
    "get_node": """
        SELECT id, workflow_id, type, prompt_contract, output, status, created_at
        FROM nodes WHERE id = $1;
    """,
    "update_node_status": """
        UPDATE nodes SET status = $1 WHERE id = $2;
    """,
    "update_node_output": """
        UPDATE nodes SET output = $1, status = $2 WHERE id = $3;
    """,
}

SQLITE_SQL = {
    # SQLite 3.35+ supports UPDATE...RETURNING (but NOT FOR UPDATE SKIP LOCKED)
    # This acts as an atomic pop without the PostgreSQL-specific syntax
    "fetch_pending_node": """
        UPDATE nodes
        SET status = 'RUNNING'
        WHERE id = (
            SELECT id FROM nodes
            WHERE status = 'PENDING'
            ORDER BY created_at ASC
            LIMIT 1
        )
        RETURNING id, workflow_id, prompt_contract;
    """,
    # SQLite uses ? placeholders
    "insert_node": """
        INSERT INTO nodes (id, workflow_id, type, prompt_contract, status)
        VALUES (?, ?, ?, ?, ?);
    """,
    "get_node": """
        SELECT id, workflow_id, type, prompt_contract, output, status, created_at
        FROM nodes WHERE id = ?;
    """,
    "update_node_status": """
        UPDATE nodes SET status = ? WHERE id = ?;
    """,
    "update_node_output": """
        UPDATE nodes SET output = ?, status = ? WHERE id = ?;
    """,
}

# Shared schema for both databases (minus PostgreSQL-specific types)
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
    prompt_contract TEXT NOT NULL,
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
    condition_rule TEXT
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

# =============================================================================
# Abstract Base DAO - Defines the contract for all database implementations
# =============================================================================


class BaseNodeDAO(ABC):
    """Abstract base for node data access operations."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection or pool."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection or pool."""
        pass

    @abstractmethod
    async def init_schema(self) -> None:
        """Initialize schema tables."""
        pass

    @abstractmethod
    async def fetch_pending_node(self) -> Optional[Dict[str, Any]]:
        """Atomically fetch and lock a PENDING node. Returns None if queue empty."""
        pass

    @abstractmethod
    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get a single node by ID."""
        pass

    @abstractmethod
    async def insert_node(
        self,
        node_id: str,
        workflow_id: str,
        node_type: str,
        prompt_contract: str,
        status: str = "PENDING",
    ) -> str:
        """Insert a new node. Returns the node ID."""
        pass

    @abstractmethod
    async def update_node_status(self, node_id: str, status: str) -> None:
        """Update a node's status."""
        pass

    @abstractmethod
    async def update_node_output(self, node_id: str, output: str, status: str) -> None:
        """Update a node's output and status."""
        pass


# =============================================================================
# PostgreSQL Implementation
# =============================================================================


class PostgresNodeDAO(BaseNodeDAO):
    """
    PostgreSQL implementation using asyncpg.

    Supports: FOR UPDATE SKIP LOCKED for safe concurrent polling.
    Optimized pool settings for 4GB RAM environments.
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None
        self._sql = POSTGRES_SQL  # Use Postgres-specific SQL

    async def connect(self) -> None:
        """Create connection pool with 4GB-optimized settings."""
        self.pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            command_timeout=60,
        )
        logger.info("PostgreSQL connection pool established")

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def init_schema(self) -> None:
        """Initialize schema (no special SQLite pragmas needed)."""
        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        logger.info("PostgreSQL schema initialized")

    async def fetch_pending_node(self) -> Optional[Dict[str, Any]]:
        """Atomic pop using FOR UPDATE SKIP LOCKED."""
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(
                    self._sql["fetch_pending_node"],
                    "RUNNING",  # New status
                    "PENDING",  # Filter condition
                )
                return dict(record) if record else None
        except Exception as e:
            logger.error(f"PostgreSQL fetch_pending_node error: {e}")
            return None

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single node."""
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(self._sql["get_node"], node_id)
            return dict(record) if record else None

    async def insert_node(
        self,
        node_id: str,
        workflow_id: str,
        node_type: str,
        prompt_contract: str,
        status: str = "PENDING",
    ) -> str:
        """Insert a new node."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                self._sql["insert_node"],
                node_id,
                workflow_id,
                node_type,
                prompt_contract,
                status,
            )
            return str(result)

    async def update_node_status(self, node_id: str, status: str) -> None:
        """Update node status."""
        async with self.pool.acquire() as conn:
            await conn.execute(self._sql["update_node_status"], status, node_id)

    async def update_node_output(self, node_id: str, output: str, status: str) -> None:
        """Update node output and status."""
        async with self.pool.acquire() as conn:
            await conn.execute(self._sql["update_node_output"], output, status, node_id)


# =============================================================================
# SQLite Implementation
# =============================================================================


class SqliteNodeDAO(BaseNodeDAO):
    """
    SQLite implementation using aiosqlite.

    ANTI-SLOP: Uses atomic UPDATE...RETURNING (SQLite 3.35+) instead of
    PostgreSQL's FOR UPDATE SKIP LOCKED. WAL mode enabled for concurrent writes.

    Note: True concurrent writes still require PostgreSQL, but WAL mode
    allows multiple readers with occasional writes without "database locked" errors.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._sql = SQLITE_SQL  # Use SQLite-specific SQL (no regex conversion!)

    async def connect(self) -> None:
        """Connect and enable SQLite-specific pragmas for concurrent safety."""
        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        # CRITICAL: Enable WAL mode for concurrent read/write safety
        # Without this, multiple writers will get "database is locked" errors
        await self._conn.execute("PRAGMA journal_mode = WAL;")

        # Also enable foreign keys (good practice)
        await self._conn.execute("PRAGMA foreign_keys = ON;")

        # Busy timeout: wait up to 5 seconds for locks instead of immediate failure
        await self._conn.execute("PRAGMA busy_timeout = 5000;")

        logger.info(f"SQLite connection established (WAL mode enabled): {self.db_path}")

    async def disconnect(self) -> None:
        """Close connection (WAL checkpoints automatically)."""
        if self._conn:
            # Close WAL and checkpoint before closing
            await self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            await self._conn.close()
            logger.info("SQLite connection closed")

    async def init_schema(self) -> None:
        """Initialize schema (split by statement to handle SQLite limitations)."""
        for statement in SCHEMA_SQL.split(";"):
            statement = statement.strip()
            if statement:
                await self._conn.execute(statement)
        await self._conn.commit()
        logger.info("SQLite schema initialized")

    async def fetch_pending_node(self) -> Optional[Dict[str, Any]]:
        """
        Atomic pop using UPDATE...RETURNING.

        SQLite 3.35+ supports RETURNING clause. This acts as an atomic pop
        without the PostgreSQL-specific FOR UPDATE SKIP LOCKED syntax.
        """
        try:
            cursor = await self._conn.execute(self._sql["fetch_pending_node"])
            row = await cursor.fetchone()

            if row:
                # Convert sqlite3.Row to dict
                return {
                    "id": row["id"],
                    "workflow_id": row["workflow_id"],
                    "prompt_contract": row["prompt_contract"],
                }
            return None
        except Exception as e:
            logger.error(f"SQLite fetch_pending_node error: {e}")
            await self._conn.rollback()
            return None

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single node."""
        cursor = await self._conn.execute(self._sql["get_node"], (node_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def insert_node(
        self,
        node_id: str,
        workflow_id: str,
        node_type: str,
        prompt_contract: str,
        status: str = "PENDING",
    ) -> str:
        """Insert a new node."""
        await self._conn.execute(
            self._sql["insert_node"],
            (node_id, workflow_id, node_type, prompt_contract, status),
        )
        await self._conn.commit()
        return node_id

    async def update_node_status(self, node_id: str, status: str) -> None:
        """Update node status."""
        await self._conn.execute(self._sql["update_node_status"], (status, node_id))
        await self._conn.commit()

    async def update_node_output(self, node_id: str, output: str, status: str) -> None:
        """Update node output and status."""
        await self._conn.execute(
            self._sql["update_node_output"], (output, status, node_id)
        )
        await self._conn.commit()

    async def fetchall(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """
        Generic fetchall for ad-hoc queries (use sparingly).
        Only supports ? placeholders - caller must use correct syntax.
        """
        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def execute(self, query: str, params: tuple = ()) -> None:
        """Generic execute for ad-hoc writes."""
        await self._conn.execute(query, params)
        await self._conn.commit()


# =============================================================================
# Factory Function - Create correct DAO based on DSN
# =============================================================================


def create_node_dao(dsn: str) -> BaseNodeDAO:
    """
    Factory function to create the correct DAO based on database URL.

    Args:
        dsn: Database URL (e.g., "sqlite:///path/to/db.db" or
             "postgresql://user:pass@localhost/dbname")

    Returns:
        Appropriate DAO instance (SqliteNodeDAO or PostgresNodeDAO)

    Raises:
        ValueError: If database scheme is not recognized
    """
    if dsn.startswith("sqlite"):
        db_path = dsn.replace("sqlite:///", "")
        return SqliteNodeDAO(db_path)
    elif dsn.startswith("postgresql") or dsn.startswith("postgres"):
        return PostgresNodeDAO(dsn)
    else:
        raise ValueError(f"Unsupported database scheme: {dsn.split('://')[0]}")


# =============================================================================
# Global Instance - Created based on current settings
# =============================================================================

# Lazy-loaded DAO instance
_dao_instance: Optional[BaseNodeDAO] = None


async def get_dao() -> BaseNodeDAO:
    """
    Get or create the global DAO instance.

    ANTI-SLOP: Uses lazy initialization to avoid importing settings at module
    load time, which can cause circular import issues.
    """
    global _dao_instance
    if _dao_instance is None:
        _dao_instance = create_node_dao(settings.database_url)
        await _dao_instance.connect()
        await _dao_instance.init_schema()
    return _dao_instance


async def close_dao() -> None:
    """Close the global DAO instance."""
    global _dao_instance
    if _dao_instance:
        await _dao_instance.disconnect()
        _dao_instance = None


# =============================================================================
# Legacy Compatibility - Wrappers that maintain old API
# =============================================================================
# These allow existing code to continue working while using the new DAO


class LegacyDatabaseWrapper:
    """
    Compatibility wrapper that presents the old Database API
    while delegating to the new DAO underneath.

    ANTI-SLOP: This wrapper exists only for backward compatibility during
    the transition. New code should use get_dao() directly.
    """

    def __init__(self, dao: BaseNodeDAO):
        self._dao = dao
        self.is_sqlite = isinstance(dao, SqliteNodeDAO)

    async def connect(self) -> None:
        await self._dao.connect()
        await self._dao.init_schema()

    async def disconnect(self) -> None:
        await self._dao.disconnect()

    async def init_schema(self) -> None:
        await self._dao.init_schema()

    # Delegate specific methods
    async def fetch_pending_node(self) -> Optional[Dict[str, Any]]:
        return await self._dao.fetch_pending_node()

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return await self._dao.get_node(node_id)

    async def insert_node(
        self,
        node_id: str,
        workflow_id: str,
        node_type: str,
        prompt_contract: str,
        status: str = "PENDING",
    ) -> str:
        return await self._dao.insert_node(
            node_id, workflow_id, node_type, prompt_contract, status
        )

    async def update_node_status(self, node_id: str, status: str) -> None:
        await self._dao.update_node_status(node_id, status)

    async def update_node_output(self, node_id: str, output: str, status: str) -> None:
        await self._dao.update_node_output(node_id, output, status)


# For legacy code that imports `db` from this module
db = None  # Will be initialized by init_db()


async def init_db() -> LegacyDatabaseWrapper:
    """Initialize the legacy-compatible database wrapper."""
    global db
    dao = await get_dao()
    db = LegacyDatabaseWrapper(dao)
    return db


# =============================================================================
# Legacy Exports - For backward compatibility with existing code
# =============================================================================


async def create_pool(dsn: str) -> LegacyDatabaseWrapper:
    """
    Legacy wrapper for create_pool() calls.

    For PostgreSQL, returns a wrapper that can be used as if it were an asyncpg Pool.
    For SQLite, returns a wrapper that provides a similar interface.
    """
    dao = create_node_dao(dsn)
    await dao.connect()
    await dao.init_schema()
    return LegacyDatabaseWrapper(dao)


# Alias for pool getter (legacy API)
async def get_pool():
    """
    Legacy alias - returns the DAO for code that expected a pool.

    NOTE: The DAO has different methods than asyncpg Pool.
    New code should use get_dao() directly.
    """
    return await get_dao()
