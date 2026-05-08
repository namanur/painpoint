"""
Pydantic Validation Engine for Stage 1.2: Level 1 & Level 2 Gates
"""

from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any


class PromptContract(BaseModel):
    """
    The immutable Prompt Contract schema.
    
    Level 1 (Syntax Validation): Pydantic enforces field types and constraints.
    Level 2 (Semantic Validation): model_validator enforces logical consistency.
    
    Note: Level 3 (Business Rules) is enforced separately in validators/business_rules.py
    """
    
    role: str = Field(..., min_length=10, max_length=500, 
                      description="The agent's role description")
    
    constraints: List[str] = Field(
        default_factory=list,
        description="Constraints the agent must obey"
    )
    
    allowed_tools: List[str] = Field(
        default_factory=list,
        description="Tools this agent is allowed to use"
    )
    
    forbidden_actions: List[str] = Field(
        default_factory=list,
        description="Actions this agent must never take"
    )
    
    decision_rules: Dict[str, str] = Field(
        default_factory=dict,
        description="Rules for graph progression (e.g., {'success': 'node_2'})"
    )
    
    max_retries: int = Field(
        default=3,
        le=5,
        description="Maximum retry attempts (hard limit: 5)"
    )
    
    @model_validator(mode='after')
    def validate_tool_isolation(self) -> 'PromptContract':
        """
        Level 2: Semantic Validation - Tools cannot be both allowed and forbidden.
        
        Anti-Slop: No fuzzy matching. Contradictions cause hard failures.
        """
        allowed_set = set(self.allowed_tools)
        forbidden_set = set(self.forbidden_actions)
        intersection = allowed_set & forbidden_set
        
        if intersection:
            raise ValueError(
                f"Contradiction: Tools cannot be both allowed and forbidden. "
                f"Overlap: {intersection}"
            )
        
        return self
    
    @model_validator(mode='after')
    def validate_max_retries(self) -> 'PromptContract':
        """Level 2: Semantic validation for retry bounds."""
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        # Note: le=5 in Field() already enforces the upper bound
        return self


def validate_level_0(raw_json: str) -> Dict[str, Any]:
    """
    Level 1 Entry Point: Parse raw JSON string.
    
    Returns:
        Parsed dictionary if valid JSON
        
    Raises:
        json.JSONDecodeError: If JSON is malformed (Level 1 failure)
    """
    import json
    return json.loads(raw_json)


def validate_level_1_and_2(parsed_dict: Dict[str, Any]) -> PromptContract:
    """
    Level 1 & 2 Validation: Parse and validate the Prompt Contract.
    
    Returns:
        Validated PromptContract instance
        
    Raises:
        ValidationError: If schema or semantics are invalid
    """
    return PromptContract(**parsed_dict)


def full_validation_pipeline(raw_json: str) -> PromptContract:
    """
    Complete validation pipeline: Level 0 -> Level 1 -> Level 2 -> Level 3.
    
    This is the main entry point for validating LLM-generated contracts.
    
    Returns:
        Validated PromptContract
        
    Raises:
        json.JSONDecodeError: Level 1 failure (invalid JSON syntax)
        ValidationError: Level 2/3 failure (schema or semantic violation)
    """
    parsed = validate_level_0(raw_json)
    return validate_level_1_and_2(parsed)
