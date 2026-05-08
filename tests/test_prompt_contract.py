"""
Tests for PromptContract Pydantic model (Stage 1.2).
Covers Level 1 (Syntax) and Level 2/3 (Semantic/Business) validation.
"""

import pytest
import json
from src.models.prompt_contract import (
    PromptContract,
    validate_level_0,
    validate_level_1_and_2,
    full_validation_pipeline,
)


class TestPromptContractValidation:
    """Test Level 1 (Syntax) and Level 2/3 (Semantic/Business) validation."""
    
    def test_valid_contract(self):
        """A valid contract should pass all validation levels."""
        contract = PromptContract(
            role="A helpful assistant that processes data",
            allowed_tools=["mcp_read", "mcp_search"],
            forbidden_actions=["delete_data"],
            max_retries=3,
        )
        assert contract.role.startswith("A helpful")
        assert "mcp_read" in contract.allowed_tools
        assert contract.max_retries == 3
    
    def test_role_length_validation(self):
        """Role must be between 10 and 500 characters (Level 1)."""
        # Too short
        with pytest.raises(Exception):
            PromptContract(
                role="Short",
                allowed_tools=[],
            )
        
        # Valid
        contract = PromptContract(
            role="This is a valid role description that is long enough",
            allowed_tools=[],
        )
        assert contract.role
    
    def test_max_retries_ceiling(self):
        """max_retries cannot exceed 5 (Level 2 semantic check)."""
        with pytest.raises(Exception):
            PromptContract(
                role="A valid role description here",
                max_retries=10,  # Exceeds le=5 constraint
            )
    
    def test_tool_isolation_contradiction(self):
        """Tools cannot be both allowed and forbidden (Level 2)."""
        with pytest.raises(ValueError, match="Contradiction"):
            PromptContract(
                role="A valid role description for testing",
                allowed_tools=["mcp_database_write"],
                forbidden_actions=["mcp_database_write"],
            )
    
    def test_write_requires_approval(self):
        """Write access requires human approval tool (Level 3 business rule)."""
        from src.validators.business_rules import enforce_level_3, BusinessRuleViolation
        
        contract = PromptContract(
            role="A valid role description for database operations",
            allowed_tools=["mcp_database_write"],
            # Missing "human_approval" in allowed_tools
        )
        # This should raise BusinessRuleViolation (not ValueError)
        # because the enforcement is in business_rules.py, not in the model
        with pytest.raises(BusinessRuleViolation):
            enforce_level_3(contract)
    
    def test_write_with_approval_valid(self):
        """Write access with human approval should pass."""
        contract = PromptContract(
            role="A valid role description for database operations",
            allowed_tools=["mcp_database_write", "human_approval"],
            forbidden_actions=[],
        )
        assert "human_approval" in contract.allowed_tools
    
    def test_multiple_contradictions(self):
        """Multiple contradictory tools should all be reported."""
        with pytest.raises(ValueError, match="Contradiction"):
            PromptContract(
                role="A valid role description here",
                allowed_tools=["tool_a", "tool_b", "tool_c"],
                forbidden_actions=["tool_a", "tool_c"],  # Two contradictions
            )


class TestLevel0Parsing:
    """Test Level 0: Raw JSON parsing."""
    
    def test_valid_json(self):
        """Valid JSON should parse successfully."""
        raw = '{"role": "A test role that is long enough", "allowed_tools": []}'
        result = validate_level_0(raw)
        assert "role" in result
        assert result["role"] == "A test role that is long enough"
    
    def test_invalid_json(self):
        """Invalid JSON should raise JSONDecodeError."""
        raw = '{"role": "missing closing brace"'
        with pytest.raises(Exception):  # json.JSONDecodeError
            validate_level_0(raw)
    
    def test_empty_string(self):
        """Empty string should fail."""
        with pytest.raises(Exception):
            validate_level_0("")


class TestFullPipeline:
    """Test the complete validation pipeline."""
    
    def test_pipeline_valid_contract(self):
        """Complete pipeline with valid contract."""
        raw_json = json.dumps({
            "role": "A helpful assistant for data processing tasks",
            "allowed_tools": ["mcp_read"],
            "forbidden_actions": ["delete_all"],
            "max_retries": 2,
        })
        contract = full_validation_pipeline(raw_json)
        assert isinstance(contract, PromptContract)
        assert contract.max_retries == 2
    
    def test_pipeline_invalid_json(self):
        """Pipeline should fail on invalid JSON (Level 1)."""
        with pytest.raises(Exception):  # JSONDecodeError
            full_validation_pipeline('{invalid json}')
    
    def test_pipeline_contradiction(self):
        """Pipeline should fail on contradictory tools (Level 2)."""
        raw_json = json.dumps({
            "role": "A test role description that is sufficiently long",
            "allowed_tools": ["conflicting_tool"],
            "forbidden_actions": ["conflicting_tool"],
        })
        with pytest.raises(ValueError, match="Contradiction"):
            full_validation_pipeline(raw_json)
    
    def test_pipeline_missing_required_field(self):
        """Pipeline should fail if required field is missing (Level 1)."""
        raw_json = json.dumps({
            "allowed_tools": [],  # Missing required "role"
        })
        with pytest.raises(Exception):  # ValidationError
            full_validation_pipeline(raw_json)
