"""
Stage 4.1: The Tri-Phase Extraction Protocol

Uses an LLM as a strict compiler to interview the user and output
syntactically valid JSON arrays of PromptContracts.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from src.models.prompt_contract import PromptContract
from src.core.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# Available tools that can be used in contracts
AVAILABLE_TOOLS = [
    "mcp_database_read",
    "mcp_database_write",
    "mcp_database_drop",
    "mcp_stripe_charge",
    "mcp_email_send",
    "mcp_erpnext_read",
    "mcp_http_get",
    "mcp_file_read",
    "human_approval",
]


def get_compiler_prompt() -> str:
    """
    Get the system prompt for the Compiler Agent.
    
    Returns:
        System prompt string with schema and instructions
    """
    schema = json.dumps(PromptContract.model_json_schema(), indent=2)
    
    return f"""You are the System Compiler. Your job is to convert the user's workflow request into an array of strict PromptContracts.

You must follow the Tri-Phase Protocol internally before outputting:
1. Boundary Definition: What triggers this? What is the terminal output?
2. Logic Branching: Where are the IF/THEN decisions?
3. Resource Mapping: Which pre-approved tools are needed?

AVAILABLE TOOLS: {AVAILABLE_TOOLS}

You must output a JSON object containing a 'nodes' array. Every item in the array MUST strictly adhere to this JSON Schema:
{schema}

Do not add fields. Do not hallucinate tools. Output only valid JSON.
"""


async def compile_workflow(user_request: str) -> List[Dict[str, Any]]:
    """
    Compile a user's natural language workflow request into PromptContracts.
    
    Args:
        user_request: Natural language description of the workflow
        
    Returns:
        List of dictionaries representing valid PromptContracts
        
    Raises:
        ValueError: If the LLM output fails validation
    """
    client = await get_llm_client()
    
    system_prompt = get_compiler_prompt()
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request},
    ]
    
    try:
        response = await client.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_request}],
        )
        
        content = response.get("content", "{}")
        
        # Parse the response
        if isinstance(content, str):
            data = json.loads(content)
        else:
            data = content
        
        # Extract nodes array
        if "nodes" in data:
            nodes = data["nodes"]
        else:
            # Assume the response is the array itself
            nodes = data if isinstance(data, list) else [data]
        
        # Validate each node against the Pydantic model
        validated_nodes = []
        for node in nodes:
            contract = PromptContract(**node)
            validated_nodes.append(contract.model_dump())
        
        logger.info(f"Compiled {len(validated_nodes)} nodes from user request")
        return validated_nodes
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM output as JSON: {e}")
        raise ValueError(f"LLM output is not valid JSON: {e}")
    except Exception as e:
        logger.error(f"Compilation failed: {e}")
        raise


async def refine_workflow(
    user_request: str,
    clarification: str,
    previous_nodes: List[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Refine a workflow based on user clarification.
    
    Args:
        user_request: Original request
        clarification: User's clarification response
        previous_nodes: Previously compiled nodes (optional)
        
    Returns:
        List of refined PromptContract dictionaries
    """
    client = await get_llm_client()
    
    system_prompt = get_compiler_prompt()
    
    context = f"Original request: {user_request}\n"
    if previous_nodes:
        context += f"Previous compilation: {json.dumps(previous_nodes)}\n"
    context += f"User clarification: {clarification}"
    
    try:
        response = await client.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": context}],
        )
        
        content = response.get("content", "{}")
        
        if isinstance(content, str):
            data = json.loads(content)
        else:
            data = content
        
        nodes = data.get("nodes", data if isinstance(data, list) else [data])
        
        # Validate
        validated_nodes = []
        for node in nodes:
            contract = PromptContract(**node)
            validated_nodes.append(contract.model_dump())
        
        return validated_nodes
        
    except Exception as e:
        logger.error(f"Refinement failed: {e}")
        raise


__all__ = [
    "compile_workflow",
    "refine_workflow",
    "get_compiler_prompt",
    "AVAILABLE_TOOLS",
]
