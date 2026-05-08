"""
Core module for Phase 3: The Async Execution Engine.

This module contains:
- engine.py: Event loop and database polling
- agent.py: Agent shell that executes contracts
- tools.py: FastMCP tool binding with async safety
"""

from src.core.engine import orchestration_loop, single_execution
from src.core.agent import execute_node
from src.core.tools import get_tool_registry, execute_tool, get_mcp_server

__all__ = [
    "orchestration_loop",
    "single_execution",
    "execute_node",
    "get_tool_registry",
    "execute_tool",
    "get_mcp_server",
]
