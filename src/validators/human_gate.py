"""
Level 4 Gate: Human Approval Checkpoint (Stage 2.3)

Purpose: Identify if the validated contract requires human intervention 
before transitioning to the RUNNING state in the database.

Anti-Slop: This does not pause the thread. Waiting for human input on a 
live async thread will crash the single-process 4GB server. This function 
simply flags the database insert to mark the node as AWAITING_APPROVAL 
instead of PENDING.
"""

from typing import Set
from src.models.prompt_contract import PromptContract
from src.core.tools import get_approval_tools


def _get_approval_triggers() -> Set[str]:
    """Lazy-loaded set of approval-trigger tools from central registry."""
    return get_approval_tools()


def requires_level_4_approval(contract: PromptContract) -> bool:
    """
    Stage 2.3: Check if contract requires human approval.
    
    Returns:
        True if any tool in allowed_tools matches approval triggers
    """
    triggers = _get_approval_triggers()
    return any(
        tool in triggers 
        for tool in contract.allowed_tools
    )


def get_triggering_tools(contract: PromptContract) -> Set[str]:
    """
    Get the specific tools that triggered the approval requirement.
    
    Returns:
        Set of tools that match approval triggers
    """
    triggers = _get_approval_triggers()
    return set(contract.allowed_tools).intersection(triggers)


def get_initial_status(contract: PromptContract) -> str:
    """
    Determine the initial node status based on Level 4 check.
    
    Returns:
        "AWAITING_APPROVAL" if human approval needed, "PENDING" otherwise
    """
    if requires_level_4_approval(contract):
        return "AWAITING_APPROVAL"
    return "PENDING"
