"""
Stage 4.2: The Deterministic Graph Renderer (Mermaid)

Generates a visual Mermaid.js graph from database state.
No heavy frontend libraries - compute is done server-side.
"""

import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Mermaid node shape styles based on status
STATUS_STYLES = {
    "DRAFT": {"fill": "#e0e0e0", "stroke": "#9e9e9e"},
    "PENDING": {"fill": "#f9f9f9", "stroke": "#333333"},
    "RUNNING": {"fill": "#fff9c4", "stroke": "#f57f17"},
    "SUCCESS": {"fill": "#c8e6c9", "stroke": "#388e3c"},
    "FAILED": {"fill": "#ffcdd2", "stroke": "#d32f2f"},
    "AWAITING_APPROVAL": {"fill": "#e1bee7", "stroke": "#8e24aa"},
}


def generate_mermaid_graph(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> str:
    """
    Generate a Mermaid graph string from nodes and edges.
    
    Args:
        nodes: List of node records from database
        edges: List of edge records from database
        
    Returns:
        Mermaid graph definition string
    """
    lines = ["graph TD"]
    
    # Render Nodes with State Colors
    for node in nodes:
        node_id = str(node.get('id', node.get('node_id', 'unknown')))
        status = node.get('status', 'DRAFT')
        
        # Extract role from prompt_contract
        contract = node.get('prompt_contract', {})
        if isinstance(contract, str):
            try:
                contract = json.loads(contract)
            except json.JSONDecodeError:
                contract = {}
        
        role = contract.get('role', 'Unknown')
        # Truncate and escape role for display
        safe_role = role.replace('"', "'")[:50]
        if len(role) > 50:
            safe_role += "..."
        
        # Format: ID["Role/Action"]:::STATE
        lines.append(f'    {node_id}["{safe_role}"]:::{status}')
    
    # Render Edges
    for edge in edges:
        from_id = str(edge.get('from_node_id', edge.get('from', '')))
        to_id = str(edge.get('to_node_id', edge.get('to', '')))
        
        # Get condition from condition_rule
        condition_rule = edge.get('condition_rule', {})
        if isinstance(condition_rule, str):
            try:
                condition_rule = json.loads(condition_rule)
            except json.JSONDecodeError:
                condition_rule = {}
        
        condition = condition_rule.get('if', 'Next')
        
        lines.append(f'    {from_id} -->|"{condition}"| {to_id}')
    
    # Inject Status Styles
    for status, style in STATUS_STYLES.items():
        fill = style["fill"]
        stroke = style["stroke"]
        lines.append(f'    classDef {status} fill:{fill},stroke:{stroke};')
    
    return "\n".join(lines)


def generate_mermaid_from_workflow(
    workflow_id: str,
    pool,  # asyncpg Pool
) -> str:
    """
    Generate Mermaid graph directly from database for a given workflow.
    
    Args:
        workflow_id: UUID of the workflow
        pool: asyncpg connection pool
        
    Returns:
        Mermaid graph string
    """
    import asyncio
    
    async def _fetch():
        async with pool.acquire() as conn:
            nodes = await conn.fetch(
                "SELECT id, status, prompt_contract FROM nodes WHERE workflow_id = $1",
                workflow_id,
            )
            edges = await conn.fetch(
                "SELECT from_node_id, to_node_id, condition_rule FROM edges WHERE workflow_id = $1",
                workflow_id,
            )
            
            return [dict(n) for n in nodes], [dict(e) for e in edges]
    
    nodes, edges = asyncio.run(_fetch())
    return generate_mermaid_graph(nodes, edges)


def render_mermaid_to_html(mermaid_string: str, title: str = "Workflow Graph") -> str:
    """
    Wrap a Mermaid graph in an HTML page for rendering.
    
    Args:
        mermaid_string: The Mermaid graph definition
        title: HTML page title
        
    Returns:
        Complete HTML page with Mermaid.js
    """
    # Escape the mermaid string for JavaScript
    escaped = mermaid_string.replace("\\", "\\\\").replace("`", "\\`")
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
        }});
    </script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
        }}
        .mermaid {{
            background: white;
            padding: 20px;
            border-radius: 8px;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="mermaid">
{escaped}
    </div>
</body>
</html>"""
    
    return html


__all__ = [
    "generate_mermaid_graph",
    "generate_mermaid_from_workflow",
    "render_mermaid_to_html",
    "STATUS_STYLES",
]
