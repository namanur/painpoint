"""
Tests for business_rules (Stage 2.2: Level 3 Gate).
Covers business rule enforcement.
"""

import pytest
from src.validators.business_rules import (
    BusinessRuleViolation,
    enforce_level_3,
    check_dangerous_tools,
    requires_human_approval_tool,
    DANGEROUS_TOOLS,
)
from src.models.prompt_contract import PromptContract


class TestEnforceLevel3:
    """Test Level 3 business rule enforcement."""
    
    def test_valid_contract_passes(self):
        """A safe contract should pass all rules."""
        contract = PromptContract(
            role="A safe assistant for reading data",
            allowed_tools=["mcp_read", "mcp_search"],
            forbidden_actions=["delete_all"],
        )
        result = enforce_level_3(contract)
        assert result == contract
    
    def test_dangerous_tools_require_approval(self):
        """Dangerous tools must have human_approval in allowed_tools."""
        contract = PromptContract(
            role="A database admin role for testing",
            allowed_tools=["mcp_database_write"],  # Missing human_approval
        )
        with pytest.raises(BusinessRuleViolation, match="Level 3 Failure"):
            enforce_level_3(contract)
    
    def test_dangerous_with_approval_passes(self):
        """Dangerous tools with human_approval should pass."""
        contract = PromptContract(
            role="A database admin role with approval",
            allowed_tools=["mcp_database_write", "human_approval"],
        )
        result = enforce_level_3(contract)
        assert result == contract
    
    def test_scraper_role_retry_limit(self):
        """Scraper roles limited to 1 retry."""
        contract = PromptContract(
            role="A web scraper that collects data",
            allowed_tools=["mcp_read"],
            max_retries=3,  # Too many for scraper
        )
        with pytest.raises(BusinessRuleViolation, match="Level 3 Failure"):
            enforce_level_3(contract)
    
    def test_scraper_role_single_retry_ok(self):
        """Scraper with 1 retry should pass."""
        contract = PromptContract(
            role="A web scraper for data collection",
            allowed_tools=["mcp_read"],
            max_retries=1,
        )
        result = enforce_level_3(contract)
        assert result.max_retries == 1
    
    def test_multiple_dangerous_tools(self):
        """Multiple dangerous tools all require human_approval."""
        contract = PromptContract(
            role="Admin role with multiple dangerous tools",
            allowed_tools=["mcp_database_write", "mcp_stripe_charge"],
        )
        with pytest.raises(BusinessRuleViolation):
            enforce_level_3(contract)
    
    def test_write_and_drop_together(self):
        """Cannot have both write and drop permissions."""
        contract = PromptContract(
            role="Database admin with full permissions",
            allowed_tools=["mcp_database_write", "mcp_database_drop", "human_approval"],
        )
        with pytest.raises(BusinessRuleViolation, match="both write and drop"):
            enforce_level_3(contract)


class TestCheckDangerousTools:
    """Test dangerous tool detection."""
    
    def test_finds_dangerous_tools(self):
        contract = PromptContract(
            role="A test role for dangerous tools",
            allowed_tools=["mcp_read", "mcp_database_write", "mcp_stripe_charge"],
        )
        dangerous = check_dangerous_tools(contract)
        assert "mcp_database_write" in dangerous
        assert "mcp_stripe_charge" in dangerous
        assert "mcp_read" not in dangerous
    
    def test_no_dangerous_tools(self):
        contract = PromptContract(
            role="A safe role with no dangerous tools",
            allowed_tools=["mcp_read", "mcp_search"],
        )
        dangerous = check_dangerous_tools(contract)
        assert len(dangerous) == 0


class TestRequiresHumanApprovalTool:
    """Test human approval tool check."""
    
    def test_needs_approval(self):
        contract = PromptContract(
            role="A role that needs approval",
            allowed_tools=["mcp_stripe_charge"],
        )
        assert requires_human_approval_tool(contract) == True
    
    def test_no_approval_needed(self):
        contract = PromptContract(
            role="A safe role",
            allowed_tools=["mcp_read"],
        )
        assert requires_human_approval_tool(contract) == False
