"""
Database schema initialization for Phase 1.1: Immutable Relational Schema
"""

import asyncpg


# Stage 1.1: Immutable Relational Schema (Strict SQL)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'DRAFT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    prompt_contract JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows(id) ON DELETE CASCADE,
    from_node_id UUID REFERENCES nodes(id),
    to_node_id UUID REFERENCES nodes(id),
    condition_rule JSONB
);

CREATE TABLE IF NOT EXISTS execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID REFERENCES nodes(id) ON DELETE CASCADE,
    workflow_id UUID REFERENCES workflows(id) ON DELETE CASCADE,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db(pool: asyncpg.Pool) -> None:
    """
    Initialize the database schema.
    Creates all tables if they don't exist.
    
    Anti-Slop: Using raw SQL via asyncpg, no ORM overhead.
    """
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


async def create_pool(dsn: str, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """
    Create an asyncpg connection pool.
    
    Optimized for 4GB RAM VPS: conservative connection pooling.
    """
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
    )
