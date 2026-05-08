"""
Stage 3.2: The Base Agent Class (The Shell)

Purpose: A static Python class that hydrates its behavior entirely from
the PromptContract. It has no innate logic other than how to talk to the LLM API.

ANTI-SLOP DETERMINISTIC ROUTING:
- The LLM is a DATA TRANSFORMER, not a router.
- It produces mutated payloads, formatted tool arguments, extracted entities.
- It has ZERO awareness of workflow state or routing decisions.
- Routing is CODE-DRIVEN via JSONPath edge evaluation in the Python event loop.

Flow:
1. Hydrate PromptContract from JSON
2. Build system prompt (NO routing directives, NO decision keys)
3. Execute LLM call — returns raw data payload only
4. Evaluate outgoing edges via JSONPath against the raw output
5. Route to next node based on boolean logic (first match wins)
6. If no edge matches → FAILED state
"""

import json
import logging
from typing import Any, Optional

from src.models.prompt_contract import PromptContract
from src.core.jsonpath_evaluator import evaluate_edges
from src.core.tools import execute_tool
from src.core.llm_client import async_llm_call
from src.db.schema import get_dao, BaseNodeDAO, SqliteNodeDAO
from src.state.machine import NodeStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def execute_node(
    node_id: str,
    contract_json: str,
    workflow_id: str,
) -> None:
    """
    Execute a node based on its PromptContract.

    Flow:
    1. Hydrate PromptContract from JSON
    2. Construct system prompt (no routing directives)
    3. Execute LLM call — returns raw data payload
    4. Evaluate outgoing edges via JSONPath against the output
    5. Route to next node based on boolean logic
    6. If no edge matches, or evaluation fails → FAILED

    Args:
        node_id: UUID of the node to execute
        contract_json: JSON string of the PromptContract
        workflow_id: UUID of the parent workflow
    """
    dao = await get_dao()

    try:
        # Stage 1: Hydrate contract
        contract = PromptContract.model_validate_json(contract_json)
        logger.info(f"Node {node_id}: Executing as role '{contract.role}'")

        # Stage 2: Construct system prompt (NO routing directives)
        system_prompt = _build_system_prompt(contract)

        # Stage 3: Execute — LLM returns pure data payload, no routing keys
        raw_output = await _execute_with_retries(
            contract=contract,
            system_prompt=system_prompt,
            node_id=node_id,
            dao=dao,
        )

        # Stage 4: Code-driven routing via JSONPath edge evaluation
        await _process_execution_result(
            dao=dao,
            node_id=node_id,
            workflow_id=workflow_id,
            raw_output=raw_output,
        )

    except Exception as e:
        logger.error(f"Node {node_id}: Unhandled error: {e}")
        await _mark_failed(dao, node_id, str(e))


def _build_system_prompt(contract: PromptContract) -> str:
    """
    Construct the system prompt strictly from contract parameters.

    ANTI-SLOP: The LLM is a DATA TRANSFORMER.
    - No routing directives, no decision keys, no workflow awareness.
    - The LLM only knows its role, constraints, and available tools.
    - Routing is handled by the Python event loop via JSONPath edge evaluation.

    Returns:
        System prompt string (exact control, no template engines)
    """
    parts = [
        f"You are an agent with the following role: {contract.role}.",
    ]

    if contract.constraints:
        parts.append(
            f"You must obey these constraints: {json.dumps(contract.constraints)}."
        )

    if contract.allowed_tools:
        parts.append(
            f"You have access to these tools: {json.dumps(contract.allowed_tools)}."
        )

    # The LLM outputs ONLY the requested data transformation.
    # Routing is determined by the Python event loop, not by the LLM.
    parts.append("Output only the requested data. No extra commentary.")

    return " ".join(parts)


async def _execute_with_retries(
    contract: PromptContract,
    system_prompt: str,
    node_id: str,
    dao: BaseNodeDAO,
) -> Any:
    """
    Execute the LLM call with retry logic.

    Returns the RAW data payload — no routing keys, no decision wrappers.
    The LLM is a data transformer, not a router.

    Returns:
        Raw output data: parsed JSON dict, tool results, or plain text payload
    """
    retries = 0

    while retries <= contract.max_retries:
        try:
            logger.info(
                f"Node {node_id}: Attempt {retries + 1}/{contract.max_retries + 1}"
            )

            if retries > 0:
                await _log_execution(dao, node_id, f"Retry attempt {retries}")

            # Execute LLM call — returns pure data, no routing keys
            result = await _call_llm_as_transformer(
                system_prompt=system_prompt,
                allowed_tools=contract.allowed_tools,
            )

            logger.info(f"Node {node_id}: Execution successful")
            return result

        except Exception as e:
            retries += 1
            logger.warning(f"Node {node_id}: Attempt failed: {e}")

            if retries > contract.max_retries:
                logger.error(f"Node {node_id}: Max retries exceeded")
                raise Exception(
                    f"Max retries ({contract.max_retries}) exceeded. Last error: {e}"
                )

            await _log_execution(dao, node_id, f"Attempt failed: {e}. Retrying...")

    raise Exception("Unexpected exit from retry loop")


async def _call_llm_as_transformer(
    system_prompt: str,
    allowed_tools: list[str],
) -> Any:
    """
    Call the LLM as a pure DATA TRANSFORMER.

    The LLM produces ONLY:
    - Mutated payloads (structured data)
    - Formatted tool arguments
    - Extracted entities

    It does NOT produce:
    - Routing keys (no 'decision' field)
    - Workflow awareness
    - Orchestration instructions

    Returns:
        The raw output: parsed JSON if valid, tool results dict, or plain text
    """
    try:
        response = await async_llm_call(
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
        )

        content = response.get("content", "")

        # Parse as JSON if valid (the LLM is a data transformer)
        try:
            if isinstance(content, str):
                if content.strip():
                    result = json.loads(content)
                else:
                    result = {}
            elif isinstance(content, dict):
                result = content
            else:
                result = {"output": str(content)}
        except json.JSONDecodeError:
            # Not JSON — wrap as plain text output
            result = {"output": content}

        # Execute any tool calls made by the LLM
        if response.get("tool_calls"):
            tool_results = []
            for tc in response["tool_calls"]:
                tool_name = tc["name"]
                tool_args = tc.get("arguments", {})
                logger.info(f"Executing tool: {tool_name}")
                try:
                    tool_result = await execute_tool(tool_name, **tool_args)
                    tool_results.append(
                        {"tool": tool_name, "result": tool_result}
                    )
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    tool_results.append({"tool": tool_name, "error": str(e)})

            result["tool_results"] = tool_results

        return result

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise


async def _process_execution_result(
    dao: BaseNodeDAO,
    node_id: str,
    workflow_id: str,
    raw_output: Any,
) -> None:
    """
    Code-Driven Control Flow: Evaluate edges against raw output.

    FLOW:
    1. Capture raw output from LLM/tool execution
    2. Save output to node record
    3. Fetch outgoing edges from the database
    4. Evaluate each edge's JSONPath condition against the output
    5. Route to the first matching edge's target node
    6. If no edge matches → FAILED (unexpected payload)
    7. If no edges exist → terminal node, SUCCESS

    ANTI-SLOP: Zero LLM involvement in routing. Pure boolean logic on the CPU.
    """
    output_json = json.dumps(raw_output)

    # Step 1: Log the execution
    await _log_execution(dao, node_id, f"Execution complete")

    # Step 2: Write output and mark SUCCESS
    await dao.update_node_output(node_id, output_json, NodeStatus.SUCCESS.value)
    logger.info(f"Node {node_id}: Output saved, evaluating edges...")

    # Step 3: Fetch outgoing edges
    edges = await dao.get_outgoing_edges(node_id)

    if not edges:
        # No outgoing edges — this is a terminal node
        logger.info(f"Node {node_id}: Terminal node (no edges), marked SUCCESS")
        return

    # Step 4-5: Evaluate JSONPath conditions against raw output
    try:
        matched_node_id = evaluate_edges(raw_output, edges)
    except Exception as e:
        # Step 6a: Edge evaluation threw — FAILED
        logger.error(
            f"Node {node_id}: Edge evaluation failed: {e}. "
            f"Transitioning to FAILED."
        )
        await _log_execution(
            dao, node_id, f"Edge evaluation error: {e}. Node failed."
        )
        await dao.update_node_status(node_id, NodeStatus.FAILED.value)
        return

    if matched_node_id:
        # Route to the matched next node
        logger.info(
            f"Node {node_id}: Edge matched → routing to {matched_node_id}"
        )
        await _trigger_next_node(dao, workflow_id, matched_node_id)
    else:
        # Step 6b: No edge matched — FAILED
        logger.error(
            f"Node {node_id}: No edge condition matched the output. "
            f"Output: {output_json[:200]}"
        )
        await _log_execution(
            dao,
            node_id,
            f"No matching edge for output. {len(edges)} edges evaluated.",
        )
        await dao.update_node_status(node_id, NodeStatus.FAILED.value)


async def _trigger_next_node(
    dao: BaseNodeDAO,
    workflow_id: str,
    next_node_id: str,
) -> None:
    """
    Trigger the next node in the workflow graph.

    Updates the next node to PENDING so it gets picked up
    by the orchestration loop.
    """
    try:
        node = await dao.get_node(next_node_id)
        if not node:
            logger.warning(f"No node found: {next_node_id}")
            return

        # Nodes start with status from the human-gate check (PENDING or AWAITING_APPROVAL).
        # Only trigger if the node hasn't been started yet (isn't RUNNING or terminal).
        terminal_statuses = {NodeStatus.SUCCESS.value, NodeStatus.FAILED.value, NodeStatus.RUNNING.value}
        if node["status"] not in terminal_statuses:
            await dao.update_node_status(next_node_id, NodeStatus.PENDING.value)
            logger.info(f"Triggered next node {next_node_id} to PENDING")
        else:
            logger.warning(
                f"Next node {next_node_id} in terminal/running status "
                f"(current: {node['status']}) — not triggering"
            )
    except Exception as e:
        logger.error(f"Failed to trigger next node {next_node_id}: {e}")


async def _mark_failed(dao: BaseNodeDAO, node_id: str, error: str) -> None:
    """Mark a node as FAILED and log the error."""
    await _log_execution(dao, node_id, f"FAILED: {error}")
    await dao.update_node_status(node_id, NodeStatus.FAILED.value)
    logger.error(f"Node {node_id}: Marked as FAILED")


async def _log_execution(dao: BaseNodeDAO, node_id: str, message: str) -> None:
    """Append to the execution log (Level 5 auditing)."""
    import uuid

    try:
        log_id = str(uuid.uuid4())
        if isinstance(dao, SqliteNodeDAO):
            await dao.execute(
                "INSERT INTO execution_logs (id, node_id, level, message) "
                "VALUES (?, ?, ?, ?)",
                (log_id, node_id, "INFO", message),
            )
        else:
            await dao.execute(
                "INSERT INTO execution_logs (id, node_id, level, message) "
                "VALUES ($1, $2, $3, $4)",
                (log_id, node_id, "INFO", message),
            )
    except Exception as e:
        logger.error(f"Failed to log execution: {e}")