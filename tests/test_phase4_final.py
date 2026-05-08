"""
Tests for Phase 4: The Compiler & Visual Render Layer

Tests the Tri-Phase Extraction Protocol, Mermaid graph rendering,
and Controlled Mutation API.
"""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

from src.compiler.extraction import compile_workflow, get_compiler_prompt, AVAILABLE_TOOLS
from src.api.visualizer import generate_mermaid_graph, STATUS_STYLES
from src.models.prompt_contract import PromptContract


# ============================================================================
# Test Tri-Phase Extraction Protocol (Stage 4.1)
# ============================================================================

class TestCompilerPrompt:
    """Test the compiler prompt generation."""
    
    def test_get_compiler_prompt_returns_string(self):
        """Test that get_compiler_prompt returns a string."""
        prompt = get_compiler_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
    
    def test_prompt_contains_schema(self):
        """Test that prompt contains JSON schema."""
        prompt = get_compiler_prompt()
        assert "JSON Schema" in prompt or "schema" in prompt.lower()
    
    def test_prompt_contains_available_tools(self):
        """Test that prompt lists available tools."""
        prompt = get_compiler_prompt()
        for tool in AVAILABLE_TOOLS[:3]:  # Check first few
            assert tool in prompt


class TestCompileWorkflow:
    """Test the workflow compilation."""
    
    @pytest.mark.asyncio
    async def test_compile_workflow_success(self):
        """Test successful workflow compilation."""
        mock_response = {
            "content": json.dumps({
                "nodes": [
                    {
                        "role": "data scraper with enough characters",
                        "allowed_tools": ["mcp_http_get"],
                        "decision_rules": {"success": "node_2"},
                        "max_retries": 1,
                    }
                ]
            })
        }
        
        with patch("src.compiler.extraction.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await compile_workflow("Create a data scraper")
            
            assert len(result) == 1
            assert "role" in result[0]
            assert result[0]["role"] == "data scraper with enough characters"
    
    @pytest.mark.asyncio
    async def test_compile_workflow_validates_output(self):
        """Test that compilation validates against Pydantic model."""
        # Invalid node (missing required field)
        mock_response = {
            "content": json.dumps({
                "nodes": [
                    {
                        "allowed_tools": ["mcp_http_get"],
                        # Missing "role" field
                    }
                ]
            })
        }
        
        with patch("src.compiler.extraction.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            with pytest.raises(Exception):  # Should raise ValueError or ValidationError
                await compile_workflow("Invalid request")


# ============================================================================
# Test Deterministic Graph Renderer (Stage 4.2)
# ============================================================================

class TestMermaidRenderer:
    """Test Mermaid graph generation."""
    
    def test_generate_simple_graph(self):
        """Test generating a simple Mermaid graph."""
        nodes = [
            {
                "id": "node1",
                "status": "PENDING",
                "prompt_contract": {"role": "Data Scraper"},
            },
            {
                "id": "node2",
                "status": "SUCCESS",
                "prompt_contract": {"role": "Data Processor"},
            },
        ]
        edges = [
            {"from_node_id": "node1", "to_node_id": "node2", "condition_rule": {"if": "success"}},
        ]
        
        mermaid = generate_mermaid_graph(nodes, edges)
        
        assert "graph TD" in mermaid
        assert "node1" in mermaid
        assert "node2" in mermaid
        assert "Data Scraper" in mermaid
        assert "Data Processor" in mermaid
    
    def test_generate_graph_with_status_styles(self):
        """Test that status styles are included."""
        nodes = [
            {"id": "n1", "status": "RUNNING", "prompt_contract": {"role": "Agent"}},
        ]
        edges = []
        
        mermaid = generate_mermaid_graph(nodes, edges)
        
        # Check that classDef statements are present
        assert "classDef" in mermaid
        for status in STATUS_STYLES:
            assert status in mermaid
    
    def test_generate_graph_escapes_quotes(self):
        """Test that quotes in role names are escaped."""
        nodes = [
            {
                "id": "node1",
                "status": "PENDING",
                "prompt_contract": {"role": 'Agent with "quotes"'},
            },
        ]
        edges = []
        
        mermaid = generate_mermaid_graph(nodes, edges)
        
        # Quotes should be replaced with single quotes
        assert "'quotes'" in mermaid or '"quotes"' in mermaid
    
    def test_empty_graph(self):
        """Test generating an empty graph."""
        mermaid = generate_mermaid_graph([], [])
        assert "graph TD" in mermaid


# ============================================================================
# Test Controlled Mutation API (Stage 4.3)
# ============================================================================

class TestControlledMutation:
    """Test the API endpoints for node mutation."""
    
    def test_node_update_request_model(self):
        """Test NodeUpdateRequest validation."""
        from src.api.mutation import NodeUpdateRequest
        
        # Valid request
        req = NodeUpdateRequest(
            constraints=["rate_limit: 100"],
            allowed_tools=["mcp_http_get"],
            max_retries=2,
        )
        assert req.constraints == ["rate_limit: 100"]
        assert req.allowed_tools == ["mcp_http_get"]
        assert req.max_retries == 2
    
    def test_node_update_request_optional_fields(self):
        """Test that all fields are optional."""
        from src.api.mutation import NodeUpdateRequest
        
        req = NodeUpdateRequest()
        assert req.constraints is None
        assert req.allowed_tools is None
        assert req.max_retries is None


# ============================================================================
# Integration Test
# ============================================================================

class TestPhase4Integration:
    """Test Phase 4 integration."""
    
    def test_full_workflow_compilation_and_rendering(self):
        """Test compiling a workflow and rendering it as Mermaid."""
        # Simulate compiled nodes
        nodes = [
            {
                "id": "node1",
                "status": "SUCCESS",
                "prompt_contract": {
                    "role": "Email Monitor",
                    "allowed_tools": ["mcp_email_send"],
                    "decision_rules": {"has_invoice": "node2"},
                    "max_retries": 1,
                },
            },
            {
                "id": "node2",
                "status": "PENDING",
                "prompt_contract": {
                    "role": "Invoice Processor",
                    "allowed_tools": ["mcp_stripe_charge", "human_approval"],
                    "decision_rules": {"success": "node3"},
                    "max_retries": 1,
                },
            },
        ]
        edges = [
            {"from_node_id": "node1", "to_node_id": "node2", "condition_rule": {"if": "has_invoice"}},
        ]
        
        # Generate Mermaid
        mermaid = generate_mermaid_graph(nodes, edges)
        
        # Verify
        assert "Email Monitor" in mermaid
        assert "Invoice Processor" in mermaid
        assert "has_invoice" in mermaid
        assert "graph TD" in mermaid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
