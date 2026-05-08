"""
Level 3 Gate: Business Rule Engine (Stage 2.2)

Purpose: Enforce operational reality that a schema validator cannot know.
Connects the isolated contract to external system realities.

Anti-Slop: The LLM is completely blind to this file. Code enforces the law.
"""

from typing import List, Set
from src.models.prompt_contract import PromptContract
from src.core.tools import get_dangerous_tools, get_approval_tools


class BusinessRuleViolation(Exception):
    """Raised when a business rule is violated (Level 3 failure)."""
    pass


def _get_dangerous_tools() -> Set[str]:
    """Lazy-loaded set of dangerous tools from central registry."""
    return get_dangerous_tools()


def _get_human_approval_triggers() -> Set[str]:
    """Lazy-loaded set of approval-trigger tools from central registry."""
    return get_approval_tools()


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
    dangerous = _get_dangerous_tools()
    requested_danger: Set[str] = (
        set(contract.allowed_tools).intersection(dangerous)
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
    dangerous = _get_dangerous_tools()
    return set(contract.allowed_tools).intersection(dangerous)


def requires_human_approval_tool(contract: PromptContract) -> bool:
    """
    Check if contract has tools that should trigger Level 4.
    
    This is separate from the Level 3 enforcement - it's a flag check.
    """
    triggers = _get_human_approval_triggers()
    return bool(
        set(contract.allowed_tools).intersection(triggers)
    )
