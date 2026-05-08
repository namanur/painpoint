"""
Tests for human_gate (Stage 2.3: Level 4 Gate).
Covers human approval requirement detection.
"""

import pytest
from src.validators.human_gate import (
    requires_level_4_approval,
    get_initial_status,
    get_triggering_tools,
    APPROVAL_TRIGGERS,
)
from src.models.prompt_contract import PromptContract


class TestRequiresLevel4Approval:
    """Test Level 4 approval detection."""
    
    def test_no_trigger_returns_false(self):
        """Tools outside trigger list return False."""
        contract = PromptContract(
            role="A safe assistant for reading data",
            allowed_tools=["mcp_read", "mcp_search"],
        )
        assert requires_level_4_approval(contract) == False
    
    def test_stripe_charge_triggers(self):
        """mcp_stripe_charge should trigger approval."""
        contract = PromptContract(
            role="A payment processor role",
            allowed_tools=["mcp_stripe_charge"],
        )
        assert requires_level_4_approval(contract) == True
    
    def test_database_drop_triggers(self):
        """mcp_database_drop should trigger approval."""
        contract = PromptContract(
            role="A database admin role",
            allowed_tools=["mcp_database_drop"],
        )
        assert requires_level_4_approval(contract) == True
    
    def test_email_send_triggers(self):
        """mcp_email_send should trigger approval."""
        contract = PromptContract(
            role="An email sender role",
            allowed_tools=["mcp_email_send"],
        )
        assert requires_level_4_approval(contract) == True
    
    def test_multiple_tools_with_trigger(self):
        """If any tool triggers, returns True."""
        contract = PromptContract(
            role="Mixed tools role",
            allowed_tools=["mcp_read", "mcp_stripe_charge", "mcp_search"],
        )
        assert requires_level_4_approval(contract) == True
    
    def test_no_tools(self):
        """Empty tools list should return False."""
        contract = PromptContract(
            role="A role with no tools",
            allowed_tools=[],
        )
        assert requires_level_4_approval(contract) == False


class TestGetInitialStatus:
    """Test initial status determination."""
    
    def test_pending_for_safe_contract(self):
        """Safe contract gets PENDING status."""
        contract = PromptContract(
            role="A safe reading role",
            allowed_tools=["mcp_read"],
        )
        assert get_initial_status(contract) == "PENDING"
    
    def test_awaiting_approval_for_dangerous(self):
        """Dangerous contract gets AWAITING_APPROVAL status."""
        contract = PromptContract(
            role="A payment role",
            allowed_tools=["mcp_stripe_charge"],
        )
        assert get_initial_status(contract) == "AWAITING_APPROVAL"


class TestGetTriggeringTools:
    """Test getting specific triggering tools."""
    
    def test_returns_triggering_tools(self):
        contract = PromptContract(
            role="A role with multiple triggers",
            allowed_tools=["mcp_read", "mcp_stripe_charge", "mcp_email_send"],
        )
        triggers = get_triggering_tools(contract)
        assert "mcp_stripe_charge" in triggers
        assert "mcp_email_send" in triggers
        assert "mcp_read" not in triggers
    
    def test_no_triggers_returns_empty(self):
        contract = PromptContract(
            role="Safe role with enough chars",
            allowed_tools=["mcp_read"],
        )
        triggers = get_triggering_tools(contract)
        assert len(triggers) == 0


class TestApprovalTriggersConstant:
    """Test the APPROVAL_TRIGGERS constant."""
    
    def test_contains_expected_tools(self):
        assert "mcp_stripe_charge" in APPROVAL_TRIGGERS
        assert "mcp_database_drop" in APPROVAL_TRIGGERS
        assert "mcp_email_send" in APPROVAL_TRIGGERS
    
    def test_is_frozenset_or_set(self):
        assert isinstance(APPROVAL_TRIGGERS, set)
