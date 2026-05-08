"""
JSONPath Edge Evaluator

Evaluates edge condition_rules against node output payloads using
lightweight JSONPath expressions. No third-party dependencies.

ANTI-SLOP: This is a purpose-built evaluator, not a full JSONPath library.
We only need the subset needed for routing decisions.

Supported operators:
  ==, !=, >, <, >=, <=, is_null, is_not_null, contains, in

Supported JSONPath patterns:
  $.field           — simple field
  $.nested.field    — nested field
  $[0].field        — array index access
  $.field[0]        — array index in path
"""

import json
import operator
from typing import Any, Dict, Optional


def _resolve_path(data: Any, path: str) -> Any:
    """
    Resolve a simplified JSONPath expression against a data structure.

    Examples:
      "$.http_status"       -> data["http_status"]
      "$.payload.error"     -> data["payload"]["error"]
      "$[0].id"             -> data[0]["id"]
      "$.items[0].name"     -> data["items"][0]["name"]

    Args:
        data: The data structure (dict or list)
        path: Simplified JSONPath string

    Returns:
        The resolved value, or _MISSING sentinel if path not found
    """
    if not path.startswith("$"):
        path = "$." + path

    # Strip leading "$"
    remaining = path[1:]  # e.g. ".http_status" or "[0].id"
    current = data

    while remaining:
        # Consume leading dot or bracket
        if remaining.startswith("."):
            remaining = remaining[1:]
            # Read the next key (up to dot, bracket, or end)
            key = ""
            while remaining and remaining[0] not in (".", "["):
                key += remaining[0]
                remaining = remaining[1:]
            if not key:
                return _MISSING
            if isinstance(current, dict):
                if key not in current:
                    return _MISSING
                current = current[key]
            else:
                return _MISSING

        elif remaining.startswith("["):
            remaining = remaining[1:]
            # Read the index (up to ']')
            idx_str = ""
            while remaining and remaining[0] != "]":
                idx_str += remaining[0]
                remaining = remaining[1:]
            if not remaining or remaining[0] != "]":
                return _MISSING
            remaining = remaining[1:]  # consume ']'
            try:
                idx = int(idx_str)
            except ValueError:
                return _MISSING
            if isinstance(current, (list, tuple)):
                if idx < 0 or idx >= len(current):
                    return _MISSING
                current = current[idx]
            else:
                return _MISSING

        else:
            # Invalid path syntax
            return _MISSING

    return current


# Sentinel for missing values
class _MISSING:
    def __repr__(self):
        return "<MISSING>"

_MISSING = _MISSING()


# Operator dispatch table
_OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "contains": lambda a, b: b in a if isinstance(a, (str, list)) else False,
    "in": lambda a, b: a in b if isinstance(b, (str, list, dict)) else False,
}


def evaluate_condition(payload: Any, condition: Dict[str, Any]) -> bool:
    """
    Evaluate a single edge condition against a payload.

    Condition format:
      {"jsonpath": "$.http_status", "operator": "==", "value": 200}
      {"jsonpath": "$.payload.error", "operator": "is_null"}
      {"jsonpath": "$.payload.items", "operator": "is_not_null"}
      {"jsonpath": "$.payload.status", "operator": "in", "value": ["ok", "done"]}
      {"jsonpath": "$.payload.message", "operator": "contains", "value": "error"}

    Args:
        payload: The node output data (dict, list, or scalar)
        condition: The condition dictionary from the edge's condition_rule

    Returns:
        True if the condition is met, False otherwise
    """
    if not condition or not isinstance(condition, dict):
        # Empty or invalid condition — default to True (always route)
        return True

    jsonpath = condition.get("jsonpath", "$")
    operator_name = condition.get("operator", "==")
    expected_value = condition.get("value")

    actual_value = _resolve_path(payload, jsonpath)

    # Handle null operators
    if operator_name == "is_null":
        return isinstance(actual_value, _MISSING.__class__) or actual_value is None
    if operator_name == "is_not_null":
        return not (isinstance(actual_value, _MISSING.__class__) or actual_value is None)

    # Guard: if value is missing, condition fails
    if isinstance(actual_value, _MISSING.__class__):
        return False

    # Lookup and apply the operator
    op_func = _OPERATORS.get(operator_name)
    if op_func is None:
        raise ValueError(f"Unknown operator: {operator_name}")

    try:
        return bool(op_func(actual_value, expected_value))
    except (TypeError, ValueError):
        return False


def evaluate_edges(payload: Any, edges: list) -> Optional[str]:
    """
    Evaluate all outgoing edges against a payload.

    Args:
        payload: The node output data
        edges: List of edge dicts, each with 'to_node_id' and 'condition_rule'

    Returns:
        The to_node_id of the first matching edge, or None if no match

    The first matching edge wins. If an edge has no condition_rule,
    it acts as a default/else branch.
    """
    for edge in edges:
        condition_raw = edge.get("condition_rule")
        condition = {}
        if isinstance(condition_raw, str):
            try:
                condition = json.loads(condition_raw)
            except (json.JSONDecodeError, TypeError):
                condition = {}
        elif isinstance(condition_raw, dict):
            condition = condition_raw

        if evaluate_condition(payload, condition):
            return edge["to_node_id"]

    return None
