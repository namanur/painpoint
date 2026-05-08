"""
PainPoint Agent Orchestrator - Main Entry Point

Usage:
    python -m src.main              # Show menu
    python -m src.main setup         # Run Phase 1 setup
    python -m src.main validate      # Test Phase 2 validation
    python -m src.main run           # Start Phase 3 engine
    python -m src.main api           # Start Phase 4 API server
    python -m src.main test          # Run pytest tests
"""

import asyncio
import sys

from src.config import settings
from src.db.schema import create_pool, init_db


async def setup_phase1():
    """Initialize Phase 1: Database schema and state machine."""
    print("=" * 60)
    print("Lean Agent Orchestrator - Phase 1 Setup")
    print("The Relational Core & State Manager")
    print("=" * 60)

    # Create connection pool
    print(f"\n[1/3] Connecting to database...")
    try:
        from src.db.schema import db

        await db.connect()
        print(f"  ✓ Connected to: {db.dsn}")
    except Exception as e:
        print(f"  ✗ Failed to connect: {e}")
        return False

    # Initialize schema
    print(f"\n[2/3] Initializing database schema...")
    try:
        await db.init_schema()
        print("  ✓ Schema created (workflows, nodes, edges, execution_logs)")
    except Exception as e:
        print(f"  ✗ Failed to initialize schema: {e}")
        return False

    # Verify tables
    print(f"\n[3/3] Verifying Phase 1 components...")
    tables = ["workflows", "nodes", "edges", "execution_logs"]
    for table in tables:
        if db.is_sqlite:
            query = "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=$1"
        else:
            query = "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)"

        exists = await db.fetchval(query, table)
        # SQLite returns count, PG returns boolean
        status = "✓" if exists else "✗"
        print(f"  {status} {table}")

    # Test state machine
    print(f"\n[Bonus] State Machine verification...")
    from src.state.machine import NodeStatus, state_machine

    try:
        result = state_machine.transition(NodeStatus.PENDING, NodeStatus.RUNNING)
        print(f"  ✓ State transition: PENDING -> {result.value}")
    except Exception as e:
        print(f"  ✗ State machine error: {e}")

    print(f"\n{'=' * 60}")
    print("Phase 1 setup complete!")
    print(f"{'=' * 60}\n")

    await db.disconnect()
    return True


async def test_phase2():
    """Test Phase 2: Validation pipeline."""
    print("=" * 60)
    print("Testing Phase 2: Validation Pipeline")
    print("=" * 60)

    from src.validators.business_rules import BusinessRuleViolation, enforce_level_3
    from src.validators.human_gate import requires_level_4_approval
    from src.validators.syntax_parser import CompilationError, run_level_1_and_2

    # Test 1: Valid contract
    print("\n[Test 1] Valid contract...")
    valid_json = """{
        "role": "data_scraper with enough characters",
        "constraints": ["rate_limit: 100/day"],
        "allowed_tools": ["mcp_erpnext_read"],
        "decision_rules": {"success": "node_2"},
        "max_retries": 1
    }"""
    try:
        contract = run_level_1_and_2(valid_json)
        print(f"  ✓ Contract validated: {contract.role}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

    # Test 2: Dangerous tools without approval
    print("\n[Test 2] Business rule enforcement...")
    dangerous_json = """{
        "role": "admin with enough characters",
        "allowed_tools": ["mcp_database_write"],
        "decision_rules": {},
        "max_retries": 1
    }"""
    try:
        contract = run_level_1_and_2(dangerous_json)
        enforce_level_3(contract)
        print(f"  ✗ Should have failed!")
        return False
    except BusinessRuleViolation:
        print(f"  ✓ Correctly rejected dangerous tools without approval")

    # Test 3: Human approval check
    print("\n[Test 3] Human approval checkpoint...")
    approval_json = """{
        "role": "admin with enough characters",
        "allowed_tools": ["mcp_stripe_charge", "human_approval"],
        "decision_rules": {},
        "max_retries": 1
    }"""
    try:
        contract = run_level_1_and_2(approval_json)
        needs_approval = requires_level_4_approval(contract)
        print(f"  ✓ Requires approval: {needs_approval}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

    print(f"\n{'=' * 60}")
    print("Phase 2 validation pipeline working!")
    print(f"{'=' * 60}\n")
    return True


async def run_phase3():
    """Start Phase 3: Execution engine."""
    print("=" * 60)
    print("Starting Phase 3: Execution Engine")
    print("=" * 60)
    print("\nPress Ctrl+C to stop.\n")

    from src.core.engine import orchestration_loop

    try:
        await orchestration_loop(poll_interval=2.0, max_concurrent=5)
    except KeyboardInterrupt:
        print("\nShutdown signal received.")

    # Close pool
    from src.db import close_pool

    await close_pool()


async def run_phase4_api():
    """Start Phase 4: API server."""
    print("=" * 60)
    print("Starting Phase 4: API Server")
    print("=" * 60)

    try:
        import uvicorn
    except ImportError:
        print("\n✗ uvicorn not installed. Install with: pip install uvicorn")
        return

    print("\nStarting API server at http://localhost:8000")
    print("API docs available at http://localhost:8000/docs\n")

    from src.api import app

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Main entry point with command routing."""
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if not args or args[0] == "menu":
        print("Lean Agent Orchestrator")
        print("=" * 60)
        print("Usage:")
        print("  python -m src.main setup    - Run Phase 1 setup")
        print("  python -m src.main validate - Test Phase 2 validation")
        print("  python -m src.main run      - Start Phase 3 engine")
        print("  python -m src.main api      - Start Phase 4 API server")
        print("  python -m src.main test     - Run pytest tests")
        return

    command = args[0]

    if command == "setup":
        await setup_phase1()
    elif command == "validate":
        await test_phase2()
    elif command == "run":
        await run_phase3()
    elif command == "api":
        await run_phase4_api()
    elif command == "test":
        import subprocess

        result = subprocess.run(["pytest", "tests/", "-v"])
        sys.exit(result.returncode)
    else:
        print(f"Unknown command: {command}")
        print("Use: setup, validate, run, api, test, or menu")


if __name__ == "__main__":
    asyncio.run(main())
