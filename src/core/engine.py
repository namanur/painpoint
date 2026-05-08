"""
Stage 3.1: The Event Loop & Database Polling

Purpose: Fetch PENDING nodes from the database without race conditions
and feed them into the execution thread.

Anti-Slop Doctrine:
- Do NOT use Celery, Redis queues, or RabbitMQ for message passing
- PostgreSQL: Use FOR UPDATE SKIP LOCKED for concurrent worker safety
- SQLite: Use atomic UPDATE...RETURNING (SQLite 3.35+)
- The database IS the queue

NOTE: The DAO abstraction handles the correct SQL for each database.
Engine code should work identically regardless of the backend.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from src.core.agent import execute_node
from src.db.schema import BaseNodeDAO, get_dao

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Shutdown flag for graceful exit
_shutdown_requested = False


def _handle_shutdown(signum, frame):
    """Signal handler for SIGINT/SIGTERM."""
    global _shutdown_requested
    if _shutdown_requested:
        logger.warning("Force exit requested. Severing tasks.")
        sys.exit(1)

    _shutdown_requested = True
    logger.info("Shutdown requested. Completing current tasks...")


# Register signal handlers
signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)


async def orchestration_loop(
    poll_interval: float = 2.0,
    max_concurrent: int = 5,
) -> None:
    """
    Main event loop that polls for PENDING nodes and executes them.

    ANTI-SLOP: Uses DAO abstraction - works with PostgreSQL OR SQLite
    without requiring the engine to know which one is in use.

    Args:
        poll_interval: Seconds to wait between polls when idle
        max_concurrent: Maximum number of concurrent execution tasks
    """
    global _shutdown_requested
    dao = await get_dao()

    logger.info("Starting orchestration loop...")
    logger.info(
        f"Database backend: {'SQLite (WAL mode)' if dao.__class__.__name__ == 'SqliteNodeDAO' else 'PostgreSQL'}"
    )

    # Track running tasks for concurrency control
    running_tasks: set[asyncio.Task] = set()

    try:
        while not _shutdown_requested:
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

            # Fetch and lock a PENDING node using DAO abstraction
            # CRITICAL: No try/except here. Crash loudly if DB is down.
            record = await dao.fetch_pending_node()

            if record:
                logger.info(f"Dispatching node {record['id']} for execution")

                # Create task and track it
                task = asyncio.create_task(
                    execute_node(
                        node_id=str(record["id"]),
                        contract_json=record["prompt_contract"],
                        workflow_id=str(record["workflow_id"]),
                    )
                )
                running_tasks.add(task)
            else:
                # No pending nodes, throttle to save CPU
                await asyncio.sleep(poll_interval)

    finally:
        if running_tasks:
            logger.info(f"Awaiting {len(running_tasks)} in-flight tasks...")
            await asyncio.gather(*running_tasks, return_exceptions=True)

        from src.db.schema import close_dao

        await close_dao()
        logger.info("Engine shutdown complete.")


async def single_execution(node_id: str) -> None:
    """
    Execute a single node by ID (useful for testing or manual triggers).

    NOTE: Unlike orchestration_loop, this requires a PENDING node
    and manually marks it RUNNING before execution.

    Args:
        node_id: The UUID of the node to execute
    """
    dao = await get_dao()

    # Fetch the node
    record = await dao.get_node(node_id)

    if not record:
        raise ValueError(f"Node {node_id} not found")

    if record["status"] != "PENDING":
        raise ValueError(f"Node {node_id} is not PENDING (current: {record['status']})")

    # Mark as RUNNING
    await dao.update_node_status(node_id, "RUNNING")

    # Execute
    await execute_node(
        node_id=str(record["id"]),
        contract_json=record["prompt_contract"],
        workflow_id=str(record["workflow_id"]),
    )


if __name__ == "__main__":
    # Entry point for running the loop
    asyncio.run(orchestration_loop())
