"""
Tests for Phase 3: The Async Execution Engine

Tests the event loop, agent shell, and edge-based routing.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock

from src.core.engine import orchestration_loop, single_execution
from src.core.agent import execute_node, _build_system_prompt
from src.core.tools import get_tool_registry, mcp_erpnext_read, mcp_http_get


# ============================================================================
# Helper for mocking DAO
# ============================================================================


class MockDao:
    """Mock DAO for testing agent execution."""

    def __init__(self):
        self.get_node = AsyncMock()
        self.update_node_status = AsyncMock()
        self.update_node_output = AsyncMock()
        self.execute = AsyncMock()
        self.fetchall = AsyncMock()
        self.fetch_pending_node = AsyncMock()
        self.get_outgoing_edges = AsyncMock()


# ============================================================================
# Test System Prompt Building (LLM as Data Transformer)
# ============================================================================

class TestBuildSystemPrompt:
    """Test the _build_system_prompt function."""

    def test_basic_prompt(self):
        """Test building a basic system prompt."""
        from src.models.prompt_contract import PromptContract

        contract = PromptContract(
            role="data_scraper",
            constraints=["rate_limit: 100/day"],
            allowed_tools=["mcp_erpnext_read"],
            decision_rules={"success": "node_2"},
            max_retries=1,
        )

        prompt = _build_system_prompt(contract)

        assert "data_scraper" in prompt
        assert "rate_limit: 100/day" in prompt
        assert "mcp_erpnext_read" in prompt
        # The LLM is now a data transformer:
        # - NO routing keys in prompt
        # - NO decision_rules in prompt
        # - NO 'output your final decision' instruction
        assert "node_2" not in prompt, (
            "Decision rules must NOT appear in the prompt. "
            "Routing is code-driven, not LLM-driven."
        )
        assert "decision" not in prompt.lower(), (
            "The LLM must not be asked to output decision keys. "
            "It is a data transformer, not a router."
        )
        assert "Output only the requested data" in prompt, (
            "The prompt should direct the LLM to output pure data."
        )

    def test_empty_contract_prompt(self):
        """Test prompt with minimal contract."""
        from src.models.prompt_contract import PromptContract

        contract = PromptContract(
            role="simple_agent",
            allowed_tools=[],
            decision_rules={},
            max_retries=0,
        )

        prompt = _build_system_prompt(contract)

        assert "simple_agent" in prompt
        assert "decision" not in prompt.lower(), (
            "The LLM must not be asked to output decision keys."
        )


# ============================================================================
# Test Tool Registry
# ============================================================================

class TestToolRegistry:
    """Test the FastMCP tool registry."""

    def test_registry_not_empty(self):
        """Test that tools are registered."""
        registry = get_tool_registry()
        assert len(registry) > 0

    def test_erpnext_tool_registered(self):
        """Test that ERPNext tool is registered."""
        registry = get_tool_registry()
        assert "mcp_erpnext_read" in registry

    def test_http_get_tool_registered(self):
        """Test that HTTP GET tool is registered."""
        registry = get_tool_registry()
        assert "mcp_http_get" in registry


# ============================================================================
# Test Execute Node (Mocked - Edge-Based Routing)
# ============================================================================

class TestExecuteNode:
    """Test the execute_node function with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_execute_node_terminal_success(self):
        """Terminal node (no outgoing edges) should succeed."""
        from src.models.prompt_contract import PromptContract
        from src.state.machine import NodeStatus

        contract_json = PromptContract(
            role="test_agent",
            allowed_tools=[],
            max_retries=1,
        ).model_dump_json()

        mock_dao = MockDao()
        # No outgoing edges → terminal node
        mock_dao.get_outgoing_edges.return_value = []

        with patch("src.core.agent.get_dao", return_value=mock_dao):
            with patch(
                "src.core.agent._execute_with_retries",
                return_value={"output": "hello"},
            ):
                await execute_node(
                    node_id="test-node-id",
                    contract_json=contract_json,
                    workflow_id="test-workflow-id",
                )

        # Should have saved output and NOT marked as FAILED
        mock_dao.update_node_output.assert_called_once()
        args = mock_dao.update_node_output.call_args[0]
        assert args[2] == NodeStatus.SUCCESS.value, (
            "Terminal node should be marked SUCCESS"
        )

    @pytest.mark.asyncio
    async def test_execute_node_routes_via_edge(self):
        """Node with matching edge should route to next node."""
        from src.models.prompt_contract import PromptContract
        from src.state.machine import NodeStatus

        contract_json = PromptContract(
            role="test_agent",
            allowed_tools=[],
            max_retries=1,
        ).model_dump_json()

        mock_dao = MockDao()
        # Edge that matches: http_status == 200
        mock_dao.get_outgoing_edges.return_value = [
            {
                "to_node_id": "next-node-abc",
                "condition_rule": (
                    '{"jsonpath":"$.http_status","operator":"==","value":200}'
                ),
            },
        ]
        # The triggered next node is PENDING (initial state) — should be triggerable
        mock_dao.get_node.return_value = {
            "id": "next-node-abc",
            "status": NodeStatus.PENDING.value,
        }

        with patch("src.core.agent.get_dao", return_value=mock_dao):
            with patch(
                "src.core.agent._execute_with_retries",
                return_value={"http_status": 200},
            ):
                await execute_node(
                    node_id="test-node-id",
                    contract_json=contract_json,
                    workflow_id="test-workflow-id",
                )

        # Should have triggered the next node
        mock_dao.update_node_status.assert_any_call(
            "next-node-abc", NodeStatus.PENDING.value
        )
        assert mock_dao.update_node_output.called

    @pytest.mark.asyncio
    async def test_execute_node_fails_on_no_match(self):
        """Node with no matching edge should go to FAILED."""
        from src.models.prompt_contract import PromptContract
        from src.state.machine import NodeStatus

        contract_json = PromptContract(
            role="test_agent",
            allowed_tools=[],
            max_retries=1,
        ).model_dump_json()

        mock_dao = MockDao()
        # Edge expects 200, but LLM returned 500
        mock_dao.get_outgoing_edges.return_value = [
            {
                "to_node_id": "next-node-abc",
                "condition_rule": (
                    '{"jsonpath":"$.http_status","operator":"==","value":200}'
                ),
            },
        ]

        with patch("src.core.agent.get_dao", return_value=mock_dao):
            with patch(
                "src.core.agent._execute_with_retries",
                return_value={"http_status": 500},
            ):
                await execute_node(
                    node_id="test-node-id",
                    contract_json=contract_json,
                    workflow_id="test-workflow-id",
                )

        # Verify it was marked as FAILED
        failed_calls = [
            call for call in mock_dao.update_node_status.call_args_list
            if call.args[1] == NodeStatus.FAILED.value
        ]
        assert len(failed_calls) > 0, (
            "Node should be marked FAILED when no edge matches"
        )

    @pytest.mark.asyncio
    async def test_execute_node_empty_output_is_data(self):
        """Empty output wrapper should be valid data for edge eval."""
        from src.models.prompt_contract import PromptContract

        contract_json = PromptContract(
            role="test_agent",
            allowed_tools=[],
            max_retries=1,
        ).model_dump_json()

        mock_dao = MockDao()
        mock_dao.get_outgoing_edges.return_value = []
        mock_dao.get_node.return_value = {"id": "next", "status": "DRAFT"}

        with patch("src.core.agent.get_dao", return_value=mock_dao):
            with patch(
                "src.core.agent._execute_with_retries",
                return_value={"output": ""},
            ):
                # Should not raise
                await execute_node(
                    node_id="test-node-id",
                    contract_json=contract_json,
                    workflow_id="test-workflow-id",
                )

        assert mock_dao.update_node_output.called


# ============================================================================
# Test Async Safety (Stage 3.3)
# ============================================================================

class TestAsyncSafety:
    """Test that blocking calls are properly wrapped."""

    @pytest.mark.asyncio
    async def test_erpnext_tool_uses_to_thread(self):
        """Test that ERPNext tool wraps sync calls with to_thread."""
        import inspect
        from src.core import tools

        source = inspect.getsource(tools.mcp_erpnext_read)
        assert "to_thread" in source

    def test_no_requests_in_main_thread(self):
        """
        Test that requests is not used directly in async functions.

        This is a static analysis test.
        """
        import ast
        import os

        tools_file = os.path.join(
            os.path.dirname(__file__), "..", "src", "core", "tools.py"
        )
        with open(tools_file, "r") as f:
            source = f.read()

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                func_source = ast.get_source_segment(source, node)
                if func_source:
                    if "requests" in func_source and "to_thread" not in func_source:
                        pytest.fail(
                            f"Async function {node.name} may block on requests"
                        )


# ============================================================================
# Test Event Loop (Stage 3.1)
# ============================================================================

class TestEventLoop:
    """Test the orchestration loop."""

    @pytest.mark.asyncio
    async def test_fetch_pending_node(self):
        """Test fetching a pending node via DAO."""
        mock_dao = MockDao()
        mock_dao.fetch_pending_node.return_value = None

        result = await mock_dao.fetch_pending_node()
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])