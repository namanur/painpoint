"""
Stage 3.3: FastMCP Tool Binding

Purpose: Attach tools to the LLM securely. FastMCP provides the interface, 
but the execution must respect the single-process event loop.

Anti-Slop: Never assume a third-party library is async-safe. Wrap sync 
calls in asyncio.to_thread().
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("PainPointOrchestrator")

# Tool registry for looking up tools by name
_tool_registry: Dict[str, Callable] = {}


def get_tool_registry() -> Dict[str, Callable]:
    """
    Get the tool registry.
    
    Returns:
        Dictionary mapping tool names to their callable functions
    """
    return _tool_registry


def register_tool(name: str, func: Callable) -> None:
    """
    Register a tool in the registry.
    
    Args:
        name: Tool name (e.g., "mcp_erpnext_read")
        func: Async callable that implements the tool
    """
    _tool_registry[name] = func


# ============================================================================
# Example Tools
# ============================================================================

def _sync_scrape_erpnext(endpoint: str) -> str:
    """
    Synchronous function to scrape ERPNext.
    
    WARNING: This is a blocking call. Must be wrapped with asyncio.to_thread().
    """
    import requests
    
    logger.info(f"Syncing scraping ERPNext endpoint: {endpoint}")
    try:
        response = requests.get(endpoint, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"ERPNext scrape failed: {e}")
        raise


@mcp.tool()
async def mcp_erpnext_read(endpoint: str) -> str:
    """
    Reads data from ERPNext.
    
    Args:
        endpoint: The API endpoint to read from
        
    Returns:
        The response text
    """
    try:
        # Offload blocking sync call to background thread
        result = await asyncio.to_thread(_sync_scrape_erpnext, endpoint)
        return str(result)
    except Exception as e:
        return f"Tool execution failed: {e}"


def _sync_http_get(url: str, timeout: int = 30) -> str:
    """
    Synchronous HTTP GET request.
    
    WARNING: Blocking call - wrap with asyncio.to_thread().
    """
    import requests
    
    logger.info(f"Sync HTTP GET: {url}")
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


@mcp.tool()
async def mcp_http_get(url: str, timeout: int = 30) -> str:
    """
    Make an HTTP GET request.
    
    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        The response text
    """
    try:
        result = await asyncio.to_thread(_sync_http_get, url, timeout)
        return result
    except Exception as e:
        return f"HTTP GET failed: {e}"


def _sync_read_file(filepath: str) -> str:
    """
    Synchronous file read.
    
    WARNING: Blocking I/O - wrap with asyncio.to_thread().
    """
    logger.info(f"Sync reading file: {filepath}")
    with open(filepath, 'r') as f:
        return f.read()


@mcp.tool()
async def mcp_file_read(filepath: str) -> str:
    """
    Read a file from the filesystem.
    
    Args:
        filepath: Path to the file to read
        
    Returns:
        The file contents
    """
    try:
        result = await asyncio.to_thread(_sync_read_file, filepath)
        return result
    except Exception as e:
        return f"File read failed: {e}"


# Dangerous tools (require human_approval in contract)

def _sync_database_write(query: str, params: tuple = None) -> str:
    """
    Synchronous database write operation.
    
    WARNING: This is dangerous and requires human_approval.
    """
    # Placeholder - actual implementation would use asyncpg or similar
    logger.warning(f"Database write (blocking): {query[:100]}...")
    return f"Would execute: {query}"


@mcp.tool()
async def mcp_database_write(query: str, params: tuple = None) -> str:
    """
    Write to the database.
    
    WARNING: Dangerous tool - requires human_approval in contract.
    
    Args:
        query: SQL query to execute
        params: Optional query parameters
        
    Returns:
        Result message
    """
    try:
        result = await asyncio.to_thread(_sync_database_write, query, params)
        return result
    except Exception as e:
        return f"Database write failed: {e}"


def _sync_send_email(to: str, subject: str, body: str) -> str:
    """
    Synchronous email sending.
    
    WARNING: Blocking and dangerous - requires human_approval.
    """
    logger.warning(f"Sending email to {to}: {subject}")
    # Placeholder
    return f"Would send email to {to}"


@mcp.tool()
async def mcp_email_send(to: str, subject: str, body: str) -> str:
    """
    Send an email.
    
    WARNING: Dangerous tool - requires human_approval in contract.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body
        
    Returns:
        Result message
    """
    try:
        result = await asyncio.to_thread(_sync_send_email, to, subject, body)
        return result
    except Exception as e:
        return f"Email send failed: {e}"


# ============================================================================
# Tool Registry Initialization
# ============================================================================

def _initialize_registry():
    """Initialize the tool registry with all registered MCP tools."""
    # Register all MCP tools in our registry
    register_tool("mcp_erpnext_read", mcp_erpnext_read)
    register_tool("mcp_http_get", mcp_http_get)
    register_tool("mcp_file_read", mcp_file_read)
    register_tool("mcp_database_write", mcp_database_write)
    register_tool("mcp_email_send", mcp_email_send)
    
    logger.info(f"Tool registry initialized with {len(_tool_registry)} tools")


# Initialize on import
_initialize_registry()


async def execute_tool(tool_name: str, **kwargs) -> Any:
    """
    Execute a tool by name with the given arguments.
    
    Args:
        tool_name: Name of the tool to execute
        **kwargs: Arguments to pass to the tool
        
    Returns:
        The tool execution result
        
    Raises:
        ValueError: If tool not found in registry
    """
    if tool_name not in _tool_registry:
        raise ValueError(f"Tool '{tool_name}' not found in registry")
    
    tool_func = _tool_registry[tool_name]
    
    logger.info(f"Executing tool: {tool_name}")
    return await tool_func(**kwargs)


def get_mcp_server() -> FastMCP:
    """Get the FastMCP server instance."""
    return mcp


# Export the MCP server for external use (e.g., SSE transport)
__all__ = [
    "mcp",
    "get_tool_registry",
    "execute_tool",
    "register_tool",
    "get_mcp_server",
]
