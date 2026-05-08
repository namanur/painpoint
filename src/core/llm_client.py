"""
LLM Client for Phase 3: The Async Execution Engine

Provides async interface to LLM APIs (OpenAI, Anthropic, etc.)
"""

import json
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Async LLM client that supports multiple providers.
    
    Currently supports:
    - OpenAI (GPT-3.5, GPT-4)
    - Anthropic (Claude)
    - Extensible to other providers via LiteLLM
    """
    
    def __init__(
        self,
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None
    
    async def _get_client(self):
        """Lazy-load the appropriate client based on model."""
        if self._client is not None:
            return self._client
        
        # Determine provider from model name
        if self.model.startswith("gpt") or self.model.startswith("text-"):
            # OpenAI
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                return self._client
            except ImportError:
                logger.warning("openai package not installed. Using mock client.")
                return self._get_mock_client()
        
        elif self.model.startswith("claude"):
            # Anthropic
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self.api_key)
                return self._client
            except ImportError:
                logger.warning("anthropic package not installed. Using mock client.")
                return self._get_mock_client()
        
        else:
            # Default to mock for testing
            logger.info(f"No specific client for model {self.model}. Using mock.")
            return self._get_mock_client()
    
    def _get_mock_client(self):
        """Return a mock client for testing."""
        if self._client is None:
            self._client = MockLLMClient()
        return self._client
    
    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]] = None,
        tools: List[Dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request to the LLM.
        
        Args:
            system_prompt: The system prompt string
            messages: List of message dicts (optional, for multi-turn)
            tools: List of tool definitions (OpenAI format)
            **kwargs: Additional arguments for the API
            
        Returns:
            Dictionary with 'content', 'tool_calls', etc.
        """
        client = await self._get_client()
        
        full_messages = [{"role": "system", "content": system_prompt}]
        if messages:
            full_messages.extend(messages)
        
        try:
            if hasattr(client, 'chat'):
                # OpenAI-style
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    tools=tools,
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                )
                return self._parse_openai_response(response)
            
            elif hasattr(client, 'messages'):
                # Anthropic-style
                response = await client.messages.create(
                    model=self.model,
                    system=system_prompt,
                    messages=messages or [],
                    tools=tools,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                return self._parse_anthropic_response(response)
            
            else:
                # Mock client
                return await client.chat(
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=tools,
                )
        
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise
    
    def _parse_openai_response(self, response) -> Dict[str, Any]:
        """Parse OpenAI API response."""
        try:
            choice = response.choices[0]
            result = {
                "content": choice.message.content,
                "raw_response": response.model_dump(),
            }
            
            if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
                result["tool_calls"] = [
                    {
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in choice.message.tool_calls
                ]
            
            return result
        except Exception as e:
            logger.error(f"Failed to parse OpenAI response: {e}")
            return {"content": None, "error": str(e)}
    
    def _parse_anthropic_response(self, response) -> Dict[str, Any]:
        """Parse Anthropic API response."""
        try:
            result = {
                "content": response.content[0].text if response.content else None,
                "raw_response": response.model_dump(),
            }
            
            # Parse tool use if present
            for block in response.content:
                if block.type == "tool_use":
                    result["tool_calls"] = [{
                        "name": block.name,
                        "arguments": block.input,
                    }]
            
            return result
        except Exception as e:
            logger.error(f"Failed to parse Anthropic response: {e}")
            return {"content": None, "error": str(e)}


class MockLLMClient:
    """
    Mock LLM client for testing and development.
    
    Returns deterministic responses based on the prompt.
    """
    
    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]] = None,
        tools: List[Dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Mock chat completion that returns a placeholder response.
        
        In tests, you can patch this to return specific responses.
        """
        logger.info(f"MockLLM: Processing prompt (first 100 chars): {system_prompt[:100]}...")
        
        # Simple decision logic for testing
        if "success" in system_prompt.lower():
            decision = "success"
        elif "fail" in system_prompt.lower():
            decision = "failure"
        else:
            decision = "success"
        
        return {
            "content": json.dumps({
                "decision": decision,
                "output": f"Mock response with decision: {decision}",
            }),
            "tool_calls": None,
        }


# Global client instance (lazy-loaded)
_llm_client: Optional[LLMClient] = None


async def get_llm_client() -> LLMClient:
    """
    Get the global LLM client instance.
    
    Returns:
        LLMClient instance
    """
    global _llm_client
    
    if _llm_client is None:
        from src.config import settings
        _llm_client = LLMClient(
            model=getattr(settings, 'llm_model', 'gpt-4'),
            api_key=getattr(settings, 'llm_api_key', None),
        )
    
    return _llm_client


async def async_llm_call(
    system_prompt: str,
    allowed_tools: List[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Convenience function for making LLM calls.
    
    Args:
        system_prompt: The system prompt
        allowed_tools: List of tool names (not used directly here,
                      tools are passed via the agent)
        **kwargs: Additional arguments for the LLM
        
    Returns:
        LLM response dictionary
    """
    client = await get_llm_client()
    
    # Convert tool names to OpenAI tool format if needed
    tools = None
    if allowed_tools:
        from src.core.tools import get_tool_registry
        registry = get_tool_registry()
        # This is a simplified version - in practice, you'd convert
        # FastMCP tools to OpenAI tool format
        tools = [{"type": "function", "function": {"name": t}} for t in allowed_tools]
    
    return await client.chat(
        system_prompt=system_prompt,
        tools=tools,
        **kwargs,
    )


__all__ = [
    "LLMClient",
    "MockLLMClient",
    "get_llm_client",
    "async_llm_call",
]
