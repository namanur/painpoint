"""
Compiler package for Phase 4: The Compiler & Visual Render Layer

Provides the Tri-Phase Extraction Protocol for converting
natural language requests into PromptContract JSON arrays.
"""

from src.compiler.extraction import (
    compile_workflow,
    refine_workflow,
    get_compiler_prompt,
)

__all__ = [
    "compile_workflow",
    "refine_workflow",
    "get_compiler_prompt",
]
