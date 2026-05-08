"""
Tests for the JSONPath Edge Evaluator.

Tests the lightweight JSONPath resolver and condition evaluator
used for Code-Driven Control Flow (deterministic routing).
"""

import pytest
from src.core.jsonpath_evaluator import (
    _resolve_path,
    evaluate_condition,
    evaluate_edges,
)


class TestResolvePath:
    """Tests for the _resolve_path function."""

    def test_simple_field(self):
        """$.http_status should resolve data['http_status']."""
        data = {"http_status": 200}
        assert _resolve_path(data, "$.http_status") == 200

    def test_nested_field(self):
        """$.payload.error should resolve data['payload']['error']."""
        data = {"payload": {"error": None}}
        assert _resolve_path(data, "$.payload.error") is None

    def test_missing_field(self):
        """Missing path should return _MISSING sentinel."""
        from src.core.jsonpath_evaluator import _MISSING

        data = {"status": "ok"}
        result = _resolve_path(data, "$.http_status")
        assert isinstance(result, _MISSING.__class__)

    def test_deeply_nested(self):
        """$.a.b.c should resolve correctly."""
        data = {"a": {"b": {"c": 42}}}
        assert _resolve_path(data, "$.a.b.c") == 42

    def test_array_index(self):
        """$[0].id should resolve data[0]['id']."""
        data = [{"id": "abc"}, {"id": "def"}]
        assert _resolve_path(data, "$[0].id") == "abc"

    def test_nested_array_index(self):
        """$.items[0].name should resolve data['items'][0]['name']."""
        data = {"items": [{"name": "foo"}, {"name": "bar"}]}
        assert _resolve_path(data, "$.items[0].name") == "foo"

    def test_out_of_bounds_index(self):
        """Out of bounds index should return _MISSING."""
        from src.core.jsonpath_evaluator import _MISSING

        data = [1, 2, 3]
        result = _resolve_path(data, "$[5]")
        assert isinstance(result, _MISSING.__class__)

    def test_root_path(self):
        """$ alone should return the whole data."""
        data = {"a": 1}
        assert _resolve_path(data, "$") == data

    def test_non_dict_traversal(self):
        """Traversing into a non-dict should return _MISSING."""
        from src.core.jsonpath_evaluator import _MISSING

        data = {"key": "string_value"}
        result = _resolve_path(data, "$.key.subkey")
        assert isinstance(result, _MISSING.__class__)


class TestEvaluateCondition:
    """Tests for the evaluate_condition function."""

    def test_eq_operator(self):
        """== operator should match values."""
        condition = {"jsonpath": "$.http_status", "operator": "==", "value": 200}
        assert evaluate_condition({"http_status": 200}, condition) is True
        assert evaluate_condition({"http_status": 404}, condition) is False

    def test_ne_operator(self):
        """!= operator should match values."""
        condition = {"jsonpath": "$.http_status", "operator": "!=", "value": 200}
        assert evaluate_condition({"http_status": 404}, condition) is True
        assert evaluate_condition({"http_status": 200}, condition) is False

    def test_gt_operator(self):
        """> operator should work on numbers."""
        condition = {"jsonpath": "$.http_status", "operator": ">", "value": 200}
        assert evaluate_condition({"http_status": 301}, condition) is True
        assert evaluate_condition({"http_status": 200}, condition) is False
        assert evaluate_condition({"http_status": 100}, condition) is False

    def test_lt_operator(self):
        """< operator should work on numbers."""
        condition = {"jsonpath": "$.count", "operator": "<", "value": 10}
        assert evaluate_condition({"count": 5}, condition) is True
        assert evaluate_condition({"count": 10}, condition) is False

    def test_gte_operator(self):
        """>= operator should work on numbers."""
        condition = {"jsonpath": "$.score", "operator": ">=", "value": 80}
        assert evaluate_condition({"score": 80}, condition) is True
        assert evaluate_condition({"score": 90}, condition) is True
        assert evaluate_condition({"score": 79}, condition) is False

    def test_is_null_operator(self):
        """is_null should match None or missing."""
        condition = {"jsonpath": "$.error", "operator": "is_null"}
        assert evaluate_condition({"error": None}, condition) is True
        assert evaluate_condition({"status": "ok"}, condition) is True  # missing
        assert evaluate_condition({"error": "timeout"}, condition) is False

    def test_is_not_null_operator(self):
        """is_not_null should match present non-None values."""
        condition = {"jsonpath": "$.user", "operator": "is_not_null"}
        assert evaluate_condition({"user": "alice"}, condition) is True
        assert evaluate_condition({"user": None}, condition) is False
        assert evaluate_condition({"status": "ok"}, condition) is False  # missing

    def test_contains_operator(self):
        """contains should check substring in strings."""
        condition = {
            "jsonpath": "$.message",
            "operator": "contains",
            "value": "error",
        }
        assert evaluate_condition({"message": "internal error"}, condition) is True
        assert evaluate_condition({"message": "success"}, condition) is False

    def test_in_operator(self):
        """in should check membership in a list."""
        condition = {
            "jsonpath": "$.status",
            "operator": "in",
            "value": ["ok", "done", "completed"],
        }
        assert evaluate_condition({"status": "ok"}, condition) is True
        assert evaluate_condition({"status": "failed"}, condition) is False

    def test_default_condition_is_true(self):
        """Empty or missing condition should default to True (always route)."""
        assert evaluate_condition({"a": 1}, {}) is True
        assert evaluate_condition({"a": 1}, None) is True

    def test_unknown_operator_raises(self):
        """Unknown operator should raise ValueError."""
        condition = {"jsonpath": "$.x", "operator": "unknown_op", "value": 1}
        with pytest.raises(ValueError, match="Unknown operator"):
            evaluate_condition({"x": 1}, condition)

    def test_type_mismatch_returns_false(self):
        """Comparing string to number should return False, not crash."""
        condition = {"jsonpath": "$.age", "operator": ">", "value": 18}
        assert evaluate_condition({"age": "old"}, condition) is False

    def test_http_example(self):
        """Realistic HTTP response routing."""
        payload = {"http_status": 200, "body": {"user": "alice"}}
        success = {"jsonpath": "$.http_status", "operator": "==", "value": 200}
        redirect = {"jsonpath": "$.http_status", "operator": "==", "value": 301}
        error = {"jsonpath": "$.http_status", "operator": ">=", "value": 400}

        assert evaluate_condition(payload, success) is True
        assert evaluate_condition(payload, redirect) is False
        assert evaluate_condition(payload, error) is False

    def test_error_path_example(self):
        """Realistic error detection."""
        payload = {"payload": {"error": "timeout"}}
        has_error = {"jsonpath": "$.payload.error", "operator": "is_not_null"}
        no_error = {"jsonpath": "$.payload.error", "operator": "is_null"}

        assert evaluate_condition(payload, has_error) is True
        assert evaluate_condition(payload, no_error) is False

    def test_status_in_list_example(self):
        """Realistic multi-status routing."""
        payload = {"status": "completed", "items": [1, 2, 3]}
        done = {"jsonpath": "$.status", "operator": "in", "value": ["completed", "done"]}
        pending = {"jsonpath": "$.status", "operator": "==", "value": "pending"}

        assert evaluate_condition(payload, done) is True
        assert evaluate_condition(payload, pending) is False


class TestEvaluateEdges:
    """Tests for the evaluate_edges function."""

    def test_first_match_wins(self):
        """First matching edge should be returned."""
        payload = {"http_status": 200}
        edges = [
            {"to_node_id": "node_a", "condition_rule": '{"jsonpath":"$.http_status","operator":"==","value":200}'},
            {"to_node_id": "node_b", "condition_rule": '{"jsonpath":"$.http_status","operator":"==","value":301}'},
        ]
        assert evaluate_edges(payload, edges) == "node_a"

    def test_no_match_returns_none(self):
        """No matching edge should return None."""
        payload = {"http_status": 500}
        edges = [
            {"to_node_id": "node_a", "condition_rule": '{"jsonpath":"$.http_status","operator":"==","value":200}'},
            {"to_node_id": "node_b", "condition_rule": '{"jsonpath":"$.http_status","operator":"==","value":301}'},
        ]
        assert evaluate_edges(payload, edges) is None

    def test_empty_condition_is_default(self):
        """Edge with empty condition_rule should act as default/else branch."""
        payload = {"http_status": 500}
        edges = [
            {"to_node_id": "node_success", "condition_rule": '{"jsonpath":"$.http_status","operator":"==","value":200}'},
            {"to_node_id": "node_default", "condition_rule": ""},
        ]
        assert evaluate_edges(payload, edges) == "node_default"

    def test_missing_condition_is_fallback(self):
        """Edge without condition_rule key should act as fallback."""
        payload = {"http_status": 500}
        edges = [
            {"to_node_id": "node_a", "condition_rule": '{"jsonpath":"$.http_status","operator":"==","value":200}'},
            {"to_node_id": "node_b"},  # no condition_rule → always matches
        ]
        assert evaluate_edges(payload, edges) == "node_b"

    def test_empty_edges_returns_none(self):
        """No edges at all should return None."""
        assert evaluate_edges({"a": 1}, []) is None

    def test_realistic_routing(self):
        """Realistic multi-branch HTTP workflow routing."""
        payload = {
            "http_status": 404,
            "body": {"error": "not_found"},
            "retry_count": 0,
        }
        edges = [
            {
                "to_node_id": "node_retry",
                "condition_rule": (
                    '{"jsonpath":"$.http_status","operator":"==","value":429}'
                ),
            },
            {
                "to_node_id": "node_error",
                "condition_rule": (
                    '{"jsonpath":"$.http_status","operator":">=","value":400}'
                ),
            },
            {
                "to_node_id": "node_success",
                "condition_rule": (
                    '{"jsonpath":"$.http_status","operator":"==","value":200}'
                ),
            },
        ]
        # 404 >= 400 → matches node_error first
        assert evaluate_edges(payload, edges) == "node_error"

    def test_tool_result_routing(self):
        """Routing based on tool execution result."""
        payload = {
            "tool_results": [
                {"tool": "mcp_http_get", "result": {"status": "success", "data": []}}
            ]
        }
        edges = [
            {
                "to_node_id": "node_process",
                "condition_rule": (
                    '{"jsonpath":"$.tool_results[0].result.status",'
                    '"operator":"==","value":"success"}'
                ),
            },
            {
                "to_node_id": "node_retry",
                "condition_rule": '{"jsonpath":"$.tool_results[0].result.status","operator":"==","value":"error"}',
            },
        ]
        assert evaluate_edges(payload, edges) == "node_process"

    def test_empty_data_routing(self):
        """Routing when data array is empty."""
        payload = {"items": []}
        edges = [
            {
                "to_node_id": "node_noop",
                "condition_rule": (
                    '{"jsonpath":"$.items","operator":"==","value":[]}'
                ),
            },
            {
                "to_node_id": "node_process",
                "condition_rule": '{"jsonpath":"$.items","operator":"is_not_null"}',
            },
        ]
        assert evaluate_edges(payload, edges) == "node_noop"