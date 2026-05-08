"""
Pipeline Integrator (Stage 2.4): Level 0 → Level 5

Purpose: The single entry point that orchestrates the gates and 
executes the Level 5 database transaction.

Anti-Slop: This function is strictly linear. No circular dependencies, 
no "agentic reasoning" loops. Data goes in, runs the gauntlet, 
and either dies via Exception or lands in PostgreSQL.
"""

import json
from typing import Tuple, Dict, Any
from asyncpg import Pool

from src.validators.syntax_parser import (
    CompilationError,
    run_level_1_and_2,
)
from src.validators.business_rules import (
    BusinessRuleViolation,
    enforce_level_3,
)
from src.validators.human_gate import (
    requires_level_4_approval,
    get_initial_status,
)
from src.models.prompt_contract import PromptContract
from src.state.machine import NodeStatus


class PipelineError(Exception):
    """Base exception for pipeline errors."""
    pass


class ValidationPipeline:
    """
    Stage 2.4: The Pipeline Integrator.
    
    Orchestrates Level 0 -> 1 -> 2 -> 3 -> 4 -> 5
    """
    
    def __init__(self, pool: Pool):
        self.pool = pool
    
    async def compile_and_save_contract(
        self,
        raw_llm_output: str,
        workflow_id: str,
        node_type: str = "AGENT",
    ) -> Tuple[str, str]:
        """
        The main pipeline: Level 0 → Level 5.
        
        Flow:
        - Level 0: Raw LLM string
        - Level 1: JSON syntax validation
        - Level 2: Pydantic semantic validation
        - Level 3: Business rule enforcement
        - Level 4: Human approval check
        - Level 5: Database insert
        
        Returns:
            Tuple of (node_id, initial_status)
            
        Raises:
            CompilationError: Level 1 or 2 failure
            BusinessRuleViolation: Level 3 failure
            PipelineError: Level 5 (database) failure
        """
        # Gates 1 & 2 (Level 0 -> 1 -> 2)
        contract = run_level_1_and_2(raw_llm_output)
        
        # Gate 3 (Level 3)
        contract = enforce_level_3(contract)
        
        # Gate 4 Check (Level 4)
        initial_status = get_initial_status(contract)
        
        # Gate 5 (Execution to DB)
        try:
            node_id = await self._save_node(
                workflow_id=workflow_id,
                node_type=node_type,
                contract=contract,
                status=initial_status,
            )
        except Exception as e:
            raise PipelineError(f"Level 5 Failure: Database insert failed. {e}")
        
        return node_id, initial_status
    
    async def _save_node(
        self,
        workflow_id: str,
        node_type: str,
        contract: PromptContract,
        status: str,
    ) -> str:
        """
        Level 5: Save validated contract to PostgreSQL.
        
        Anti-Slop: Only accepts validated Pydantic objects via model_dump().
                   Never accepts raw dictionaries.
        """
        contract_dict = contract.model_dump(exclude_none=True)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO nodes (workflow_id, type, prompt_contract, status)
                VALUES ($1::UUID, $2, $3::JSONB, $4)
                RETURNING id
                """,
                workflow_id,
                node_type,
                json.dumps(contract_dict),
                status,
            )
            return str(row['id'])
    
    async def save_workflow(
        self,
        name: str,
        status: str = "DRAFT",
    ) -> str:
        """Create a new workflow."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO workflows (name, status)
                VALUES ($1, $2)
                RETURNING id
                """,
                name,
                status,
            )
            return str(row['id'])
    
    async def save_edge(
        self,
        workflow_id: str,
        from_node_id: str,
        to_node_id: str,
        condition_rule: Dict[str, Any] = None,
    ) -> str:
        """Save an edge between two nodes."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO edges (workflow_id, from_node_id, to_node_id, condition_rule)
                VALUES ($1::UUID, $2::UUID, $3::UUID, $4::JSONB)
                RETURNING id
                """,
                workflow_id,
                from_node_id,
                to_node_id,
                json.dumps(condition_rule) if condition_rule else None,
            )
            return str(row['id'])
    
    async def log_execution(
        self,
        node_id: str,
        workflow_id: str,
        level: str,
        message: str,
    ) -> None:
        """Append to the execution log (Level 5 auditing)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO execution_logs (node_id, workflow_id, level, message)
                VALUES ($1::UUID, $2::UUID, $3, $4)
                """,
                node_id,
                workflow_id,
                level,
                message,
            )


# Convenience function for Level 0 -> 1 -> 2 -> 3 (without DB)
def validate_contract_pipeline(raw_llm_output: str) -> PromptContract:
    """
    Run Levels 0-3 without database operations.
    
    Useful for testing or pre-validation before saving.
    
    Returns:
        Validated PromptContract
        
    Raises:
        CompilationError: Level 1/2 failure
        BusinessRuleViolation: Level 3 failure
    """
    # Gates 1 & 2
    contract = run_level_1_and_2(raw_llm_output)
    
    # Gate 3
    contract = enforce_level_3(contract)
    
    return contract
