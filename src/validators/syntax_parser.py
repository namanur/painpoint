"""
Level 1 & Level 2 Gate: Syntax & Semantic Parsing (Stage 2.1)

Purpose: Ensure raw LLM output is syntactically valid JSON and passes 
intrinsic semantic logic via Pydantic before touching business logic.
"""

import json
import re
from typing import Dict, Any
from pydantic import ValidationError

from src.models.prompt_contract import PromptContract


class CompilationError(Exception):
    """Raised when Level 1 (syntax) or Level 2 (semantic) validation fails."""
    pass


def clean_llm_output(raw_output: str) -> str:
    """
    Clean raw LLM output by removing markdown code blocks.
    
    Anti-Slop: Handle common LLM wrapping patterns without complex parsing.
    """
    # Remove ```json and ``` markers
    cleaned = raw_output.strip()
    
    # Handle markdown code blocks
    if cleaned.startswith("```"):
        # Find closing ```
        lines = cleaned.split('\n')
        # Remove first line (```json or ```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = '\n'.join(lines).strip()
    
    return cleaned


def run_level_1_and_2(raw_llm_output: str) -> PromptContract:
    """
    Stage 2.1: Level 1 (Syntax) & Level 2 (Semantic) validation.
    
    Flow: Raw LLM string -> Clean -> JSON parse -> Pydantic validation
    
    Returns:
        Validated PromptContract instance
        
    Raises:
        CompilationError: If JSON is invalid (Level 1) or semantics fail (Level 2)
    """
    try:
        # Clean potential markdown wrapping
        clean_json_str = clean_llm_output(raw_llm_output)
        
        # Level 1: Syntax validation
        raw_dict = json.loads(clean_json_str)
        
        # Level 2: Semantic validation (Pydantic model validation)
        contract = PromptContract(**raw_dict)
        return contract
        
    except json.JSONDecodeError as e:
        raise CompilationError(f"Level 1 Failure: Invalid JSON syntax. Details: {e}")
    except ValidationError as e:
        raise CompilationError(f"Level 2 Failure: Semantic validation failed. Details: {e}")


def parse_llm_json(raw_llm_output: str) -> Dict[str, Any]:
    """
    Level 1 only: Parse JSON without full Pydantic validation.
    
    Useful for inspection before full validation.
    """
    clean_json_str = clean_llm_output(raw_llm_output)
    return json.loads(clean_json_str)
