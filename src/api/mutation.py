"""
Stage 4.3: Controlled Mutation API

FastAPI endpoints for editing node constraints without breaking the graph.
"""

import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.models.prompt_contract import PromptContract
from src.validators.syntax_parser import run_level_1_and_2, CompilationError
from src.validators.business_rules import enforce_level_3, BusinessRuleViolation
from src.validators.human_gate import requires_level_4_approval
from src.db.schema import get_dao, BaseNodeDAO, SqliteNodeDAO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["workflows"])


class NodeUpdateRequest(BaseModel):
    """Request body for updating a node."""
    
    constraints: Optional[list[str]] = None
    allowed_tools: Optional[list[str]] = None
    decision_rules: Optional[Dict[str, str]] = None
    max_retries: Optional[int] = None


class NodeUpdateResponse(BaseModel):
    """Response for node update."""
    
    success: bool
    message: str
    node_id: str
    updated_contract: Optional[Dict[str, Any]] = None


@router.post("/workflows/", response_model=Dict[str, Any])
async def create_workflow(request: Dict[str, str]) -> Dict[str, Any]:
    """Create a new workflow."""
    dao = await get_dao()
    import uuid

    workflow_id = str(uuid.uuid4())
    name = request.get("name", "New Workflow")

    if isinstance(dao, SqliteNodeDAO):
        await dao.execute(
            "INSERT INTO workflows (id, name, status) VALUES (?, ?, ?)",
            (workflow_id, name, "DRAFT"),
        )
    else:
        await dao.execute(
            "INSERT INTO workflows (id, name, status) VALUES ($1, $2, $3)",
            (workflow_id, name, "DRAFT"),
        )

    rows = await dao.fetchall(
        "SELECT id, name, status FROM workflows WHERE id = ?"
        if isinstance(dao, SqliteNodeDAO)
        else "SELECT id, name, status FROM workflows WHERE id = $1",
        (workflow_id,),
    )
    return rows[0] if rows else {"id": workflow_id, "name": name, "status": "DRAFT"}


@router.patch("/nodes/{node_id}", response_model=NodeUpdateResponse)
async def update_node(
    node_id: str,
    update: NodeUpdateRequest,
) -> NodeUpdateResponse:
    """
    Update a node's PromptContract fields.

    This endpoint:
    - Only allows mutation of internal PromptContract fields
    - Passes updates through the 5-Level Validation Pipeline
    - Prevents modification of workflow_id or id

    Args:
        node_id: UUID of the node to update
        update: The fields to update

    Returns:
        Success status and updated contract
    """
    dao = await get_dao()

    # Fetch current node
    record = await dao.get_node(node_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    # Parse current contract
    try:
        current_contract = json.loads(record["prompt_contract"])
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Failed to parse current contract")
        
        # Apply updates (only allowed fields)
        if update.constraints is not None:
            current_contract['constraints'] = update.constraints
        
        if update.allowed_tools is not None:
            current_contract['allowed_tools'] = update.allowed_tools
        
        if update.decision_rules is not None:
            current_contract['decision_rules'] = update.decision_rules
        
        if update.max_retries is not None:
            current_contract['max_retries'] = update.max_retries
        
        # Validate through Phase 2 pipeline (Level 1-4)
        try:
            # Level 1 & 2: Syntax & Semantic
            contract = run_level_1_and_2(json.dumps(current_contract))
            
            # Level 3: Business Rules
            contract = enforce_level_3(contract)
            
            # Validation passed - update the database
            updated_json = contract.model_dump_json()
            await dao.execute(
                "UPDATE nodes SET prompt_contract = ? WHERE id = ?"
                if isinstance(dao, SqliteNodeDAO)
                else "UPDATE nodes SET prompt_contract = $1 WHERE id = $2",
                (updated_json, node_id),
            )

            logger.info(f"Node {node_id} updated successfully")

            return NodeUpdateResponse(
                success=True,
                message="Node updated successfully",
                node_id=node_id,
                updated_contract=contract.model_dump(),
            )

        except CompilationError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Validation failed (Level 1-2): {str(e)}"
            )
        except BusinessRuleViolation as e:
            raise HTTPException(
                status_code=400,
                detail=f"Business rule violation (Level 3): {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected validation error: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Validation failed: {str(e)}"
            )


@router.get("/nodes/{node_id}")
async def get_node_endpoint(node_id: str) -> Dict[str, Any]:
    """Get a node's current state and contract."""
    dao = await get_dao()
    record = await dao.get_node(node_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    return record


@router.get("/workflows/{workflow_id}/graph")
async def get_workflow_graph(workflow_id: str) -> Dict[str, Any]:
    """
    Get the Mermaid graph for a workflow.

    Returns both the raw Mermaid string and node/edge data.
    """
    dao = await get_dao()

    from src.api.visualizer import generate_mermaid_graph

    if isinstance(dao, SqliteNodeDAO):
        nodes = await dao.fetchall(
            "SELECT id, status, prompt_contract FROM nodes WHERE workflow_id = ?",
            (workflow_id,),
        )
        edges = await dao.fetchall(
            "SELECT from_node_id, to_node_id, condition_rule FROM edges WHERE workflow_id = ?",
            (workflow_id,),
        )
    else:
        nodes = await dao.fetchall(
            "SELECT id, status, prompt_contract FROM nodes WHERE workflow_id = $1",
            (workflow_id,),
        )
        edges = await dao.fetchall(
            "SELECT from_node_id, to_node_id, condition_rule FROM edges WHERE workflow_id = $1",
            (workflow_id,),
        )

    mermaid = generate_mermaid_graph(nodes, edges)

    return {
        "workflow_id": workflow_id,
        "mermaid": mermaid,
        "nodes": nodes,
        "edges": edges,
    }


@router.post("/workflows/{workflow_id}/compile")
async def compile_and_create_workflow(
    workflow_id: str,
    user_request: Dict[str, str],  # {"request": "user's description"}
) -> Dict[str, Any]:
    """
    Compile a user request and create nodes in the workflow.

    Uses the Tri-Phase Extraction Protocol (Stage 4.1).
    """
    import uuid

    from src.compiler.extraction import compile_workflow

    request_text = user_request.get("request", "")
    if not request_text:
        raise HTTPException(status_code=400, detail="Missing 'request' field")

    try:
        # Compile the workflow
        nodes_data = await compile_workflow(request_text)

        # Save nodes to database
        dao = await get_dao()
        created_nodes = []

        for node_data in nodes_data:
            # Determine initial status based on Level 4 check
            from src.validators.human_gate import get_initial_status
            from src.models.prompt_contract import PromptContract

            contract = PromptContract(**node_data)
            initial_status = get_initial_status(contract)
            node_id = str(uuid.uuid4())

            if isinstance(dao, SqliteNodeDAO):
                await dao.execute(
                    "INSERT INTO nodes (id, workflow_id, type, prompt_contract, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (node_id, workflow_id, "AGENT", json.dumps(node_data), initial_status),
                )
            else:
                await dao.execute(
                    "INSERT INTO nodes (id, workflow_id, type, prompt_contract, status) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    (node_id, workflow_id, "AGENT", json.dumps(node_data), initial_status),
                )

            created_nodes.append({"id": node_id, "status": initial_status})

        return {
            "success": True,
            "message": f"Created {len(created_nodes)} nodes",
            "nodes": created_nodes,
        }

    except Exception as e:
        logger.error(f"Compilation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Compilation failed: {str(e)}")


__all__ = ["router"]
