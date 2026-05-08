"""
Tests for State Machine (Stage 1.3).
Covers hardcoded state transitions and illegal transition detection.
"""

import pytest
from src.state.machine import (
    WorkflowStatus,
    NodeStatus,
    StateMachine,
    IllegalStateTransitionError,
    state_machine,
)


class TestNodeStateTransitions:
    """Test node state machine transitions."""
    
    def setup_method(self):
        self.sm = StateMachine()
    
    def test_valid_pending_to_running(self):
        """PENDING -> RUNNING is valid."""
        result = self.sm.transition(NodeStatus.PENDING, NodeStatus.RUNNING)
        assert result == NodeStatus.RUNNING
    
    def test_valid_running_to_success(self):
        """RUNNING -> SUCCESS is valid."""
        result = self.sm.transition(NodeStatus.RUNNING, NodeStatus.SUCCESS)
        assert result == NodeStatus.SUCCESS
    
    def test_valid_running_to_failed(self):
        """RUNNING -> FAILED is valid."""
        result = self.sm.transition(NodeStatus.RUNNING, NodeStatus.FAILED)
        assert result == NodeStatus.FAILED
    
    def test_valid_running_to_awaiting_approval(self):
        """RUNNING -> AWAITING_APPROVAL is valid."""
        result = self.sm.transition(NodeStatus.RUNNING, NodeStatus.AWAITING_APPROVAL)
        assert result == NodeStatus.AWAITING_APPROVAL
    
    def test_valid_approval_to_running(self):
        """AWAITING_APPROVAL -> RUNNING is valid (human approved)."""
        result = self.sm.transition(NodeStatus.AWAITING_APPROVAL, NodeStatus.RUNNING)
        assert result == NodeStatus.RUNNING
    
    def test_valid_approval_to_failed(self):
        """AWAITING_APPROVAL -> FAILED is valid (human rejected)."""
        result = self.sm.transition(NodeStatus.AWAITING_APPROVAL, NodeStatus.FAILED)
        assert result == NodeStatus.FAILED
    
    def test_valid_failed_to_pending(self):
        """FAILED -> PENDING is valid (reset for retry)."""
        result = self.sm.transition(NodeStatus.FAILED, NodeStatus.PENDING)
        assert result == NodeStatus.PENDING
    
    def test_invalid_success_to_running(self):
        """SUCCESS -> RUNNING is invalid (terminal state)."""
        with pytest.raises(IllegalStateTransitionError):
            self.sm.transition(NodeStatus.SUCCESS, NodeStatus.RUNNING)
    
    def test_invalid_pending_to_success(self):
        """PENDING -> SUCCESS is invalid (must go through RUNNING)."""
        with pytest.raises(IllegalStateTransitionError):
            self.sm.transition(NodeStatus.PENDING, NodeStatus.SUCCESS)
    
    def test_invalid_running_to_pending(self):
        """RUNNING -> PENDING is invalid (must fail first)."""
        with pytest.raises(IllegalStateTransitionError):
            self.sm.transition(NodeStatus.RUNNING, NodeStatus.PENDING)
    
    def test_success_is_terminal(self):
        """SUCCESS state should have no valid transitions."""
        assert len(self.sm.VALID_NODE_TRANSITIONS[NodeStatus.SUCCESS]) == 0
    
    def test_can_transition_check(self):
        """can_transition should return boolean without raising."""
        assert self.sm.can_transition(NodeStatus.PENDING, NodeStatus.RUNNING) == True
        assert self.sm.can_transition(NodeStatus.SUCCESS, NodeStatus.RUNNING) == False


class TestWorkflowStateTransitions:
    """Test workflow state machine transitions."""
    
    def setup_method(self):
        self.sm = StateMachine()
    
    def test_draft_to_pending(self):
        """DRAFT -> PENDING is valid (compile and lock)."""
        result = self.sm.transition_workflow(WorkflowStatus.DRAFT, WorkflowStatus.PENDING)
        assert result == WorkflowStatus.PENDING
    
    def test_pending_to_running(self):
        """PENDING -> RUNNING is valid."""
        result = self.sm.transition_workflow(WorkflowStatus.PENDING, WorkflowStatus.RUNNING)
        assert result == WorkflowStatus.RUNNING
    
    def test_invalid_draft_to_running(self):
        """DRAFT -> RUNNING is invalid."""
        with pytest.raises(IllegalStateTransitionError):
            self.sm.transition_workflow(WorkflowStatus.DRAFT, WorkflowStatus.RUNNING)


class TestGlobalStateMachine:
    """Test the global state machine instance."""
    
    def test_global_instance(self):
        """Global state_machine should work correctly."""
        result = state_machine.transition(NodeStatus.PENDING, NodeStatus.RUNNING)
        assert result == NodeStatus.RUNNING
