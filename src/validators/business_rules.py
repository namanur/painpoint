"""
Level 3 Gate: Business Rule Engine (Stage 2.2)

Purpose: Enforce operational reality that a schema validator cannot know.
Connects the isolated contract to external system realities.

Anti-Slop: The LLM is completely blind to this file. Code enforces the law.
"""

from typing import List, Set
from src.models.prompt_contract import PromptContract


class BusinessRuleViolation(Exception):
    """Raised when a business rule is violated (Level 3 failure)."""
    pass


# Dangerous tools that require human approval
DANGEROUS_TOOLS: Set[str] = {
    "mcp_database_write",
    "mcp_database_drop",
    "mcp_stripe_charge",
    "mcp_email_send",
    "mcp_delete_user",
}

# Tools that always require human approval (Level 4 triggers)
HUMAN_APPROVAL_TRIGGERS: Set[str] = {
    "mcp_stripe_charge",
    "mcp_database_drop",
    "mcp_email_send",
    "mcp_delete_user",
}


def enforce_level_3(
    contract: PromptContract,
    existing_workflows: List[str] = None,
) -> PromptContract:
    """
    Stage 2.2: Level 3 Business Rule validation.
    
    Rules enforced:
    1. Dangerous tools require 'human_approval' in allowed_tools
    2. Scraper roles limited to 1 retry maximum
    3. (Extensible) Additional business rules
    
    Returns:
        The same PromptContract if all rules pass
        
    Raises:
        BusinessRuleViolation: If any business rule is violated
    """
    # Rule 1: High-risk tools require specific isolation
    requested_danger: Set[str] = (
        set(contract.allowed_tools).intersection(DANGEROUS_TOOLS)
    )
    
    if requested_danger and "human_approval" not in contract.allowed_tools:
        raise BusinessRuleViolation(
            f"Level 3 Failure: Tools {requested_danger} require "
            f"'human_approval' in allowed_tools."
        )
    
    # Rule 2: Execution time limits based on role
    if "scraper" in contract.role.lower() and contract.max_retries > 1:
        raise BusinessRuleViolation(
            "Level 3 Failure: Scraper roles are strictly limited to "
            "1 retry to prevent infinite hanging."
        )
    
    # Rule 3: Cannot have both mcp_database_write and mcp_database_drop
    # without extra safeguards
    if ("mcp_database_write" in contract.allowed_tools and 
        "mcp_database_drop" in contract.allowed_tools):
        raise BusinessRuleViolation(
            "Level 3 Failure: Cannot have both write and drop permissions "
            "without additional isolation measures."
        )
    
    return contract


def check_dangerous_tools(contract: PromptContract) -> Set[str]:
    """
    Check which dangerous tools are requested.
    
    Returns:
        Set of dangerous tools in the contract's allowed_tools
    """
    return set(contract.allowed_tools).intersection(DANGEROUS_TOOLS)


def requires_human_approval_tool(contract: PromptContract) -> bool:
    """
    Check if contract has tools that should trigger Level 4.
    
    This is separate from the Level 3 enforcement - it's a flag check.
    """
    return bool(
        set(contract.allowed_tools).intersection(HUMAN_APPROVAL_TRIGGERS)
    )
