"""
API package for Phase 4: The Compiler & Visual Render Layer

Provides FastAPI endpoints for:
- Visual rendering (Mermaid graphs)
- Controlled mutation of nodes
"""

from fastapi import FastAPI

from src.api.visualizer import (
    generate_mermaid_graph,
    generate_mermaid_from_workflow,
    render_mermaid_to_html,
    STATUS_STYLES,
)
from src.api.mutation import router as mutation_router

__all__ = [
    "generate_mermaid_graph",
    "generate_mermaid_from_workflow",
    "render_mermaid_to_html",
    "STATUS_STYLES",
    "mutation_router",
]


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI app with all routes
    """
    app = FastAPI(
        title="PainPoint Agent Orchestrator",
        description="Deterministic LLM Execution Engine with Visual Workflow Builder",
        version="0.1.0",
    )
    
    # Include routers
    app.include_router(mutation_router)
    
    @app.get("/")
    async def root():
        return {
            "name": "PainPoint Agent Orchestrator",
            "version": "0.1.0",
            "phases": {
                "Phase 1": "Complete - Relational Core & State Manager",
                "Phase 2": "Complete - 5-Level Validation Pipeline",
                "Phase 3": "Complete - Async Execution Engine",
                "Phase 4": "Complete - Compiler & Visual Render Layer",
            },
        }
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}
    
    return app


# Global app instance
app = create_app()
