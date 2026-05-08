"""State management package for Lean Agent Orchestrator."""

from src.state.machine import (
    WorkflowStatus,
    NodeStatus,
    IllegalStateTransitionError,
    StateMachine,
    state_machine,
)

__all__ = [
    "WorkflowStatus",
    "NodeStatus",
    "IllegalStateTransitionError",
    "StateMachine",
    "state_machine",
]
