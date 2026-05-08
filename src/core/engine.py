"""
Stage 3.1: The Event Loop & Database Polling

Purpose: Fetch PENDING nodes from PostgreSQL without race conditions 
and feed them into the execution thread.

Anti-Slop: Do not use Celery, Redis queues, or RabbitMQ. PostgreSQL 
FOR UPDATE SKIP LOCKED acts as a zero-dependency message queue.
"""

import asyncio
import logging
from typing import Optional
from asyncpg import Pool, create_pool
from asyncpg.exceptions import PostgresError

from src.core.agent import execute_node
from src.db import get_pool
from src.state.machine import NodeStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def orchestration_loop(
    poll_interval: float = 2.0,
    max_concurrent: int = 5,
) -> None:
    """
    Main event loop that polls for PENDING nodes and executes them.
    
    Args:
        poll_interval: Seconds to wait between polls when idle
        max_concurrent: Maximum number of concurrent execution tasks
    """
    pool = await get_pool()
    
    logger.info("Starting orchestration loop...")
    
    # Track running tasks for concurrency control
    running_tasks: set[asyncio.Task] = set()
    
    try:
        while True:
            # Clean up completed tasks
            done_tasks = {task for task in running_tasks if task.done()}
            for task in done_tasks:
                try:
                    exc = task.exception()
                    if exc:
                        logger.error(f"Task {task.get_name()}: failed with: {exc}")
                except asyncio.InvalidStateError:
                    pass  # Task completed without exception
            running_tasks.difference_update(done_tasks)
            
            # If at capacity, wait a bit and continue
            if len(running_tasks) >= max_concurrent:
                logger.debug(f"At max concurrency ({max_concurrent}), waiting...")
                await asyncio.sleep(0.5)
                continue
            
            # Fetch and lock a PENDING node
            record = await _fetch_pending_node(pool)
            
            if record:
                logger.info(f"Dispatching node {record['id']} for execution")
                
                # Create task and track it
                task = asyncio.create_task(
                    execute_node(
                        node_id=str(record['id']),
                        contract_json=record['prompt_contract'],
                        workflow_id=str(record['workflow_id']),
                    )
                )
                running_tasks.add(task)
                
                # Avoid blocking on task completion
                # Let it run in background
            else:
                # No pending nodes, throttle to save CPU
                await asyncio.sleep(poll_interval)
    
    except KeyboardInterrupt:
        logger.info("Received shutdown signal...")
        # Wait for running tasks to complete
        if running_tasks:
            logger.info(f"Waiting for {len(running_tasks)} tasks to complete...")
            await asyncio.gather(*running_tasks, return_exceptions=True)
        logger.info("Shutdown complete")


async def _fetch_pending_node(pool: Pool) -> Optional[dict]:
    """
    Atomically fetch and lock a PENDING node.
    
    Uses FOR UPDATE SKIP LOCKED to prevent race conditions
    when multiple workers run against the same database.
    
    Returns:
        Record dict with 'id', 'workflow_id', 'prompt_contract' or None
    """
    try:
        async with pool.acquire() as conn:
            record = await conn.fetchrow("""
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
            """, NodeStatus.RUNNING.value, NodeStatus.PENDING.value)
            
            return dict(record) if record else None
    
    except PostgresError as e:
        logger.error(f"Database error fetching pending node: {e}")
        return None


async def single_execution(node_id: str) -> None:
    """
    Execute a single node by ID (useful for testing or manual triggers).
    
    Args:
        node_id: The UUID of the node to execute
    """
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Fetch the node
        record = await conn.fetchrow("""
            SELECT id, workflow_id, prompt_contract, status
            FROM nodes
            WHERE id = $1
        """, node_id)
        
        if not record:
            raise ValueError(f"Node {node_id} not found")
        
        if record['status'] != NodeStatus.PENDING.value:
            raise ValueError(
                f"Node {node_id} is not PENDING (current: {record['status']})"
            )
        
        # Mark as RUNNING
        await conn.execute("""
            UPDATE nodes
            SET status = $1
            WHERE id = $2
        """, NodeStatus.RUNNING.value, node_id)
    
    # Execute
    await execute_node(
        node_id=str(record['id']),
        contract_json=record['prompt_contract'],
        workflow_id=str(record['workflow_id']),
    )


if __name__ == "__main__":
    # Entry point for running the loop
    asyncio.run(orchestration_loop())
