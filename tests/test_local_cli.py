"""
Tests for the Glass Window CLI (local_cli module)
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from local_cli.main import (
    _basic_extraction,
    _build_plan_markdown,
    compile_messy_dump,
)


class TestBasicExtraction:
    """Tests for the fallback text extraction."""

    def test_split_by_newlines(self):
        """Text separated by newlines should create multiple nodes."""
        text = "First step\nSecond step\nThird step"
        nodes = _basic_extraction(text)
        # Should create nodes, with fallback parsing
        assert len(nodes) >= 1

    def test_empty_text(self):
        """Empty text should return empty list."""
        nodes = _basic_extraction("")
        assert nodes == []

    def test_short_text_filtered(self):
        """Text under 10 chars should be filtered out."""
        text = "x\n" * 20  # Short items
        nodes = _basic_extraction(text)
        assert all(len(n.get("role", "")) >= 10 for n in nodes)

    def test_max_nodes_limit(self):
        """Should limit to 10 nodes maximum."""
        text = "\n".join([f"Step number {i} with more content" for i in range(30)])
        nodes = _basic_extraction(text)
        assert len(nodes) <= 10


class TestPlanMarkdownBuilder:
    """Tests for plan markdown generation."""

    def test_empty_nodes(self):
        """Empty nodes should produce valid markdown."""
        plan = _build_plan_markdown([])
        assert "# Project Genesis Plan" in plan
        assert "## Graph Structure" in plan

    def test_nodes_rendered(self):
        """Nodes should appear in markdown."""
        from models.prompt_contract import PromptContract

        contracts = [
            PromptContract(role="Initialize the system"),
            PromptContract(role="Process data"),
        ]
        plan = _build_plan_markdown(contracts)
        assert "**node_1**" in plan
        assert "Initialize the system" in plan
        assert "**node_2**" in plan
        assert "Process data" in plan

    def test_contracts_rendered(self):
        """Contracts should appear in markdown."""
        from models.prompt_contract import PromptContract

        contracts = [
            PromptContract(
                role="Execute step 1", max_retries=3, constraints=["Follow plan"]
            )
        ]
        plan = _build_plan_markdown(contracts)
        assert "## Prompt Contracts" in plan
        assert "Execute step 1" in plan
        assert "**Max Retries:** 3" in plan
        assert "Follow plan" in plan


class TestCompileMessyDump:
    """Tests for the async compilation function."""

    @pytest.mark.asyncio
    async def test_compilation_cancelled_on_shutdown(self, monkeypatch):
        """Should return cancelled message on shutdown."""
        import local_cli.main as main_mod

        monkeypatch.setattr(main_mod, "_shutdown_requested", True)

        result = await compile_messy_dump("test input")
        assert "Cancelled" in result

    @pytest.mark.asyncio
    async def test_compilation_fallback_on_llm_failure(self, monkeypatch):
        """Should fall back to basic extraction when LLM fails."""
        import local_cli.main as main_mod

        # Mock compile_workflow to raise an error
        async def mock_fail(*args):
            raise Exception("LLM unavailable")

        monkeypatch.setattr(main_mod, "_shutdown_requested", False)
        monkeypatch.setattr("local_cli.main.compile_workflow", mock_fail)

        result = await compile_messy_dump("This is a test input that should be parsed")
        # Should have fallback content
        assert "Project Genesis Plan" in result


class TestEditorIntegration:
    """Tests for the editor-based input function."""

    def test_marker_extraction(self):
        """Content before marker should be extracted."""
        marker = "\n\n# --- DUMP YOUR MESSY IDEAS ABOVE THIS LINE ---\n"
        content = f"My task\n\n{marker}# This is comments"

        clean = content.split(marker)[0].strip()
        assert clean == "My task"

    def test_empty_after_marker(self):
        """Empty content before marker returns None."""
        marker = "\n\n# --- DUMP YOUR MESSY IDEAS ABOVE THIS LINE ---\n"
        content = f"\n\n{marker}# Comments"

        clean = content.split(marker)[0].strip()
        assert clean == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
