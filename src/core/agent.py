"""
Stage 3.2: The Base Agent Class (The Shell)

Purpose: A static Python class that hydrates its behavior entirely from 
the PromptContract. It has no innate logic other than how to talk to the LLM API.

Anti-Slop: Do not import LangChain or LlamaIndex. Control the exact 
string passed to the API.
"""

import json
import logging
from typing import Optional
from asyncpg import Pool

from src.models.prompt_contract import PromptContract
from src.core.tools import get_tool_registry, execute_tool
from src.core.llm_client import async_llm_call, get_llm_client
from src.db import get_pool
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
    2. Construct system prompt from contract
    3. Execute LLM call with allowed tools
    4. Handle retries based on max_retries
    5. Process result and update state
    
    Args:
        node_id: UUID of the node to execute
        contract_json: JSON string of the PromptContract
        workflow_id: UUID of the parent workflow
    """
    pool = await get_pool()
    
    try:
        # Stage 1: Hydrate contract
        contract = PromptContract.model_validate_json(contract_json)
        logger.info(f"Node {node_id}: Executing as role '{contract.role}'")
        
        # Stage 2: Construct system prompt
        system_prompt = _build_system_prompt(contract)
        
        # Stage 3: Execute with retries
        result = await _execute_with_retries(
            contract=contract,
            system_prompt=system_prompt,
            node_id=node_id,
        )
        
        # Stage 4: Process result
        await _process_execution_result(
            pool=pool,
            node_id=node_id,
            workflow_id=workflow_id,
            contract=contract,
            result=result,
        )
        
    except Exception as e:
        logger.error(f"Node {node_id}: Unhandled error: {e}")
        await _mark_failed(pool, node_id, str(e))


def _build_system_prompt(contract: PromptContract) -> str:
    """
    Construct the system prompt strictly from contract parameters.
    
    Anti-Slop: Exact string control. No template engines or abstractions.
    """
    parts = [
        f"You are an agent with the following role: {contract.role}.",
    ]
    
    if contract.constraints:
        constraints_json = json.dumps(contract.constraints)
        parts.append(f"You must obey these constraints: {constraints_json}.")
    
    if contract.decision_rules:
        rules_json = json.dumps(contract.decision_rules)
        parts.append(f"If you reach a decision, output your routing choice based on these rules: {rules_json}.")
    
    if contract.allowed_tools:
        tools_list = json.dumps(contract.allowed_tools)
        parts.append(f"You have access to these tools: {tools_list}.")
    
    parts.append("Output your final decision as a JSON object with a 'decision' key.")
    
    return " ".join(parts)


async def _execute_with_retries(
    contract: PromptContract,
    system_prompt: str,
    node_id: str,
) -> dict:
    """
    Execute the LLM call with retry logic.
    
    Returns:
        Dictionary with execution result
    """
    pool = await get_pool()
    retries = 0
    
    while retries <= contract.max_retries:
        try:
            logger.info(f"Node {node_id}: Attempt {retries + 1}/{contract.max_retries + 1}")
            
            # Log retry attempt
            if retries > 0:
                await _log_execution(pool, node_id, f"Retry attempt {retries}")
            
            # Execute LLM call with tools
            result = await _call_llm_with_tools(
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
                raise Exception(f"Max retries ({contract.max_retries}) exceeded. Last error: {e}")
            
            # Log retry
            await _log_execution(
                pool, node_id, f"Attempt failed: {e}. Retrying..."
            )
    
    raise Exception("Unexpected exit from retry loop")


async def _call_llm_with_tools(
    system_prompt: str,
    allowed_tools: list[str],
) -> dict:
    """
    Call the LLM API with the specified tools.
    
    Returns:
        Dictionary with 'decision' and optional 'output' keys
    """
    try:
        # Call the LLM with the prompt and tools
        response = await async_llm_call(
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
        )
        
        # Parse the response to extract decision
        content = response.get("content", "{}")
        
        # Try to parse JSON from content
        try:
            if isinstance(content, str):
                result = json.loads(content)
            elif isinstance(content, dict):
                result = content
            else:
                result = {"decision": "success", "output": str(content)}
            
            # Handle tool calls if present
            if response.get("tool_calls"):
                tool_results = []
                for tc in response["tool_calls"]:
                    tool_name = tc["name"]
                    tool_args = tc.get("arguments", {})
                    logger.info(f"Executing tool: {tool_name}")
                    try:
                        tool_result = await execute_tool(tool_name, **tool_args)
                        tool_results.append({"tool": tool_name, "result": tool_result})
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        tool_results.append({"tool": tool_name, "error": str(e)})
                
                result["tool_results"] = tool_results
            
            return result
            
        except json.JSONDecodeError:
            # If not JSON, treat as plain text output
            return {
                "decision": "success",
                "output": content,
            }
        
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise


async def _process_execution_result(
    pool: Pool,
    node_id: str,
    workflow_id: str,
    contract: PromptContract,
    result: dict,
) -> None:
    """
    Process the LLM execution result and update state.
    
    Handles:
    - Writing to execution_logs
    - Updating node status to SUCCESS
    - Triggering next node based on decision_rules
    """
    # Log the execution
    await _log_execution(
        pool, node_id, f"Execution successful: {json.dumps(result)}"
    )
    
    # Mark node as SUCCESS
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE nodes
            SET status = $1, output = $2
            WHERE id = $3
        """, NodeStatus.SUCCESS.value, json.dumps(result), node_id)
    
    logger.info(f"Node {node_id}: Marked as SUCCESS")
    
    # Handle graph progression based on decision_rules
    decision = result.get("decision", "").lower()
    
    if decision in contract.decision_rules:
        next_node_id = contract.decision_rules[decision]
        await _trigger_next_node(pool, workflow_id, next_node_id)
    else:
        logger.info(f"Node {node_id}: No matching decision rule for '{decision}'")


async def _trigger_next_node(
    pool: Pool,
    workflow_id: str,
    next_node_id: str,
) -> None:
    """
    Trigger the next node in the workflow graph.
    
    Updates the next node from DRAFT to PENDING so it gets picked up
    by the orchestration loop.
    """
    async with pool.acquire() as conn:
        # Verify the edge exists
        edge = await conn.fetchrow("""
            SELECT to_node_id FROM edges
            WHERE workflow_id = $1 AND to_node_id = $2
        """, workflow_id, next_node_id)
        
        if not edge:
            logger.warning(f"No edge found to node {next_node_id}")
            return
        
        # Update next node to PENDING
        result = await conn.execute("""
            UPDATE nodes
            SET status = $1
            WHERE id = $2 AND workflow_id = $3 AND status = $4
        """, NodeStatus.PENDING.value, next_node_id, workflow_id, NodeStatus.DRAFT.value)
        
        if result == "UPDATE 1":
            logger.info(f"Triggered next node {next_node_id} to PENDING")
        else:
            logger.warning(f"Next node {next_node_id} not in DRAFT status")


async def _mark_failed(pool: Pool, node_id: str, error: str) -> None:
    """Mark a node as FAILED and log the error."""
    await _log_execution(pool, node_id, f"FAILED: {error}")
    
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE nodes
            SET status = $1
            WHERE id = $2
        """, NodeStatus.FAILED.value, node_id)
    
    logger.error(f"Node {node_id}: Marked as FAILED")


async def _log_execution(pool: Pool, node_id: str, message: str) -> None:
    """Append to the execution log (Level 5 auditing)."""
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO execution_logs (node_id, level, message)
                VALUES ($1::UUID, $2, $3)
            """, node_id, "INFO", message)
    except Exception as e:
        logger.error(f"Failed to log execution: {e}")
