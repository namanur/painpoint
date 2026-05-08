"""
Hardcoded State Machine for Stage 1.3: Level 3 Gate
"""

from enum import Enum
from typing import Dict, List
from dataclasses import dataclass, field


class WorkflowStatus(Enum):
    """Valid workflow statuses."""
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class NodeStatus(Enum):
    """Valid node statuses."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class IllegalStateTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""
    pass


@dataclass
class StateMachine:
    """
    Hardcoded state machine enforcer.
    
    Anti-Slop: Lightweight dictionary lookup, not a library.
    """
    
    # Transition matrices as class attributes (for test access)
    VALID_WORKFLOW_TRANSITIONS: Dict[WorkflowStatus, List[WorkflowStatus]] = field(
        default_factory=lambda: {
            WorkflowStatus.DRAFT: [WorkflowStatus.PENDING],
            WorkflowStatus.PENDING: [WorkflowStatus.RUNNING, WorkflowStatus.FAILED],
            WorkflowStatus.RUNNING: [
                WorkflowStatus.AWAITING_APPROVAL,
                WorkflowStatus.SUCCESS,
                WorkflowStatus.FAILED,
            ],
            WorkflowStatus.AWAITING_APPROVAL: [
                WorkflowStatus.RUNNING,
                WorkflowStatus.FAILED,
            ],
            WorkflowStatus.SUCCESS: [],  # Terminal state
            WorkflowStatus.FAILED: [WorkflowStatus.PENDING],  # Can reset to retry
        }
    )
    
    VALID_NODE_TRANSITIONS: Dict[NodeStatus, List[NodeStatus]] = field(
        default_factory=lambda: {
            NodeStatus.PENDING: [NodeStatus.RUNNING, NodeStatus.FAILED],
            NodeStatus.RUNNING: [
                NodeStatus.AWAITING_APPROVAL,
                NodeStatus.SUCCESS,
                NodeStatus.FAILED,
            ],
            NodeStatus.AWAITING_APPROVAL: [
                NodeStatus.RUNNING,
                NodeStatus.FAILED,
            ],
            NodeStatus.SUCCESS: [],  # Terminal state
            NodeStatus.FAILED: [NodeStatus.PENDING],  # Can reset to retry
        }
    )
    
    def can_transition(
        self,
        current: NodeStatus,
        target: NodeStatus,
    ) -> bool:
        """Check if a node state transition is valid."""
        allowed = self.VALID_NODE_TRANSITIONS.get(current, [])
        return target in allowed

    def transition(
        self,
        current: NodeStatus,
        target: NodeStatus,
    ) -> NodeStatus:
        """
        Execute a state transition.

        Raises:
            IllegalStateTransitionError: If transition is not allowed
        """
        if not self.can_transition(current, target):
            raise IllegalStateTransitionError(
                f"Illegal state transition: {current.value} -> {target.value}. "
                f"Valid transitions from {current.value}: "
                f"{[s.value for s in self.VALID_NODE_TRANSITIONS.get(current, [])]}"
            )
        return target
        
    def can_transition_workflow(
        self,
        current: WorkflowStatus,
        target: WorkflowStatus,
    ) -> bool:
        """Check if a workflow state transition is valid."""
        allowed = self.VALID_WORKFLOW_TRANSITIONS.get(current, [])
        return target in allowed

    def transition_workflow(
        self,
        current: WorkflowStatus,
        target: WorkflowStatus,
    ) -> WorkflowStatus:
        """
        Execute a workflow state transition.

        Raises:
            IllegalStateTransitionError: If transition is not allowed
        """
        if not self.can_transition_workflow(current, target):
            raise IllegalStateTransitionError(
                f"Illegal workflow transition: {current.value} -> {target.value}. "
                f"Valid transitions from {current.value}: "
                f"{[s.value for s in self.VALID_WORKFLOW_TRANSITIONS.get(current, [])]}"
            )
        return target


# Global state machine instance
state_machine = StateMachine()
