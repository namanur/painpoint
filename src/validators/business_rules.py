"""
Level 3 Gate: Business Rule Engine (Stage 2.2)

Purpose: Enforce operational reality that a schema validator cannot know.
Connects the isolated contract to external system realities.

Anti-Slop: The LLM is completely blind to this file. Code enforces the law.

CTO DIRECTIVE: Consolidated dangerous/approval checks into single flag.
If a tool is dangerous, it inherently requires approval. No need for
separate dangerous_tool and approval_trigger flags.
"""

from typing import List, Set

from src.core.tools import TOOL_METADATA, get_dangerous_tools
from src.models.prompt_contract import PromptContract


class BusinessRuleViolation(Exception):
    """Raised when a business rule is violated (Level 3 failure)."""

    pass


def _get_tools_requiring_approval() -> Set[str]:
    """
    Get all tools that require human approval before execution.

    ANTI-SLOP: Single source of truth from centralized metadata.
    Dangerous = requires_approval. No separate flag needed.
    """
    return {name for name, meta in TOOL_METADATA.items() if meta.dangerous}


def enforce_level_3(
    contract: PromptContract,
    existing_workflows: List[str] = None,
) -> PromptContract:
    """
    Stage 2.2: Level 3 Business Rule validation.

    Rules enforced:
    1. Dangerous tools (those requiring approval) must have 'human_approval'
       in allowed_tools
    2. Scraper roles limited to 1 retry maximum
    3. Cannot have both write and drop permissions without extra safeguards

    Returns:
        The same PromptContract if all rules pass

    Raises:
        BusinessRuleViolation: If any business rule is violated
    """
    # Rule 1: Dangerous tools require human_approval in allowed_tools
    # ANTI-SLOP: Consolidated - dangerous implies approval required
    approval_needed = _get_tools_requiring_approval()
    requested_danger: Set[str] = set(contract.allowed_tools).intersection(
        approval_needed
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
    if (
        "mcp_database_write" in contract.allowed_tools
        and "mcp_database_drop" in contract.allowed_tools
    ):
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
    dangerous = get_dangerous_tools()
    return set(contract.allowed_tools).intersection(dangerous)


def requires_human_approval(contract: PromptContract) -> bool:
    """
    Check if contract requires human approval based on dangerous tools.

    ANTI-SLOP: Simplified - dangerous tools are the only approval triggers.
    Removed redundant _get_human_approval_triggers() that was doing the
    same work as _get_tools_requiring_approval().
    """
    dangerous = get_dangerous_tools()
    return bool(set(contract.allowed_tools).intersection(dangerous))


# Alias for backward compatibility
requires_human_approval_tool = requires_human_approval
