"""
Tests for syntax_parser (Stage 2.1: Level 1 & 2 Gate).
Covers JSON parsing and Pydantic semantic validation.
"""

import pytest
from src.validators.syntax_parser import (
    CompilationError,
    run_level_1_and_2,
    clean_llm_output,
    parse_llm_json,
)


class TestCleanLlmOutput:
    """Test markdown cleaning function."""
    
    def test_strip_code_block(self):
        """Remove ```json and ``` markers."""
        raw = '```json\n{"role": "test"}\n```'
        cleaned = clean_llm_output(raw)
        assert cleaned == '{"role": "test"}'
    
    def test_no_code_block(self):
        """Pass through when no code block present."""
        raw = '{"role": "test"}'
        cleaned = clean_llm_output(raw)
        assert cleaned == raw
    
    def test_plain_backticks(self):
        """Handle plain ``` without json prefix."""
        raw = '```\n{"role": "test"}\n```'
        cleaned = clean_llm_output(raw)
        assert cleaned == '{"role": "test"}'


class TestRunLevel1And2:
    """Test the main Level 1 & 2 validation function."""
    
    def test_valid_contract(self):
        """Valid JSON should produce a PromptContract."""
        raw = '{"role": "A test role that is sufficiently long", "allowed_tools": ["mcp_read"]}'
        contract = run_level_1_and_2(raw)
        assert contract.role == "A test role that is sufficiently long"
        assert "mcp_read" in contract.allowed_tools
    
    def test_markdown_wrapped(self):
        """Handle LLM output wrapped in markdown."""
        raw = '```json\n{"role": "A test role for markdown handling", "max_retries": 2}\n```'
        contract = run_level_1_and_2(raw)
        assert contract.max_retries == 2
    
    def test_invalid_json_level1_failure(self):
        """Invalid JSON should raise CompilationError (Level 1 failure)."""
        raw = '{"role": "missing closing brace"'
        with pytest.raises(CompilationError, match="Level 1 Failure"):
            run_level_1_and_2(raw)
    
    def test_missing_required_field(self):
        """Missing required field should raise CompilationError (Level 2)."""
        raw = '{"allowed_tools": []}'  # Missing required 'role'
        with pytest.raises(CompilationError, match="Level 2 Failure"):
            run_level_1_and_2(raw)
    
    def test_tool_contradiction_level2(self):
        """Contradictory tools should fail at Level 2."""
        raw = '''{
            "role": "A test role for contradiction check",
            "allowed_tools": ["conflicting_tool"],
            "forbidden_actions": ["conflicting_tool"]
        }'''
        with pytest.raises(CompilationError, match="Level 2 Failure"):
            run_level_1_and_2(raw)
    
    def test_truncated_json(self):
        """Truncated JSON should fail at Level 1."""
        raw = '{"role": "A test that gets cut o'
        with pytest.raises(CompilationError):
            run_level_1_and_2(raw)


class TestParseLlmJson:
    """Test the Level 1 only parser."""
    
    def test_valid_json(self):
        """Valid JSON returns dict."""
        raw = '{"key": "value", "number": 123}'
        result = parse_llm_json(raw)
        assert result["key"] == "value"
        assert result["number"] == 123
    
    def test_invalid_json_raises(self):
        """Invalid JSON raises JSONDecodeError."""
        raw = 'not json at all'
        with pytest.raises(Exception):  # json.JSONDecodeError
            parse_llm_json(raw)
