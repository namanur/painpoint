# Agent Documentation

## Overview

The PainPoint Agent is a **deterministic, constraint-driven execution engine** that operates on validated `PromptContract` JSON objects. It is **not** an autonomous agent with reasoning loops—it is a compliant shell that executes exactly what the contract specifies.

## Core Principles

1. **Blind Execution**: The agent has no innate logic beyond LLM API communication. All behavior is hydrated from the `PromptContract`.
2. **No Circular Dependencies**: The agent does not modify its own contract or reason about state transitions.
3. **Single-Process Async**: Runs on a 4GB server using `asyncio` with PostgreSQL as the message queue.
4. **Tool Isolation**: Tools are explicitly declared in `allowed_tools` and wrapped for async safety.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase 2: Validation                      │
│  Raw LLM Output → Level 1-4 Gates → Valid PromptContract  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Phase 3: Execution                       │
│  PostgreSQL (PENDING) → Agent Execution → State Update     │
└─────────────────────────────────────────────────────────────┘
```

## Agent Components

### 1. PromptContract (Phase 1)
The immutable specification that drives the agent:

```python
{
    "role": "data_scraper",
    "constraints": ["rate_limit: 100/day", "timeout: 30s"],
    "allowed_tools": ["mcp_erpnext_read", "mcp_http_get"],
    "decision_rules": {"success": "node_2", "failure": "node_3"},
    "max_retries": 1
}
```

### 2. Validation Pipeline (Phase 2)
Before execution, the contract passes through:
- **Level 1**: JSON syntax validation
- **Level 2**: Pydantic semantic validation
- **Level 3**: Business rule enforcement
- **Level 4**: Human approval checkpoint
- **Level 5**: Database persistence

### 3. Execution Engine (Phase 3)

#### Event Loop (`core/engine.py`)
- Polls PostgreSQL for `PENDING` nodes using `FOR UPDATE SKIP LOCKED`
- Atomically updates status to `RUNNING` to prevent double-execution
- Fires-and-forgets execution tasks to keep the loop unblocked

#### Agent Shell (`core/agent.py`)
- Hydrates from `PromptContract`
- Constructs system prompt from contract parameters
- Executes LLM call with allowed tools
- Handles retries based on `max_retries`
- Outputs structured decisions for graph progression

#### Tool Registry (`core/tools.py`)
- FastMCP-based tool definitions
- **Critical**: All sync I/O wrapped with `asyncio.to_thread()`
- Tools explicitly mapped from `allowed_tools` array

## Execution Flow

```
1. orchestration_loop() polls DB for PENDING nodes
2. Atomically lock node (UPDATE to RUNNING with SKIP LOCKED)
3. asyncio.create_task(execute_node(node_id, contract_json))
4. execute_node():
   a. Hydrate PromptContract from JSON
   b. Construct system prompt from contract
   c. Call LLM with allowed_tools
   d. On success: mark SUCCESS, progress graph
   e. On failure: retry (up to max_retries), then mark FAILED
5. Loop continues polling
```

## State Machine (Phase 1)

```
DRAFT → PENDING → RUNNING → SUCCESS (terminal)
                      ↓
                   FAILED → PENDING (retry)
                   
AWAITING_APPROVAL → RUNNING → SUCCESS
                   → FAILED
```

## Tool Safety

### Dangerous Tools (Require `human_approval` in allowed_tools)
- `mcp_database_write`
- `mcp_database_drop`
- `mcp_stripe_charge`
- `mcp_email_send`
- `mcp_delete_user`

### Blocking Call Protection
All tools using `requests`, `urllib`, or file I/O **must** be wrapped:

```python
@mcp.tool()
async def mcp_erpnext_read(endpoint: str) -> str:
    return await asyncio.to_thread(_sync_function, endpoint)
```

## Anti-Slop Rules

1. **No Auto-Fix Libraries**: If validation fails, throw `CompilationError`. No infinite retry loops.
2. **No LangChain/LlamaIndex**: Control the exact prompt string. No abstraction layers.
3. **No Direct State Mutation by LLM**: Graph progression is handled by backend SQL, not LLM output.
4. **No Thread Blocking**: Main event loop must continue polling during tool execution.
5. **No Circular Dependencies**: Agent doesn't reason about its own contract.

## File Structure

```
src/
├── models/
│   └── prompt_contract.py    # Phase 1: Pydantic model
├── db/
│   └── schema.py              # Phase 1: PostgreSQL schema
├── state/
│   └── machine.py             # Phase 1: State transitions
├── validators/
│   ├── syntax_parser.py       # Phase 2: Level 1-2
│   ├── business_rules.py      # Phase 2: Level 3
│   └── human_gate.py          # Phase 2: Level 4
├── pipeline/
│   └── validation.py          # Phase 2: Level 0-5 integrator
├── core/
│   ├── engine.py              # Phase 3: Event loop (TODO)
│   ├── agent.py               # Phase 3: Agent shell (TODO)
│   └── tools.py               # Phase 3: Tool registry (TODO)
└── main.py                    # Entry point
```

## Verification Checklist

### Phase 1 (Complete ✅)
- [x] `PromptContract` Pydantic model
- [x] PostgreSQL schema (workflows, nodes, edges, execution_logs)
- [x] State machine with valid transitions

### Phase 2 (Complete ✅)
- [x] Level 1-2: Syntax & semantic validation
- [x] Level 3: Business rule engine
- [x] Level 4: Human approval checkpoint
- [x] Level 5: Database persistence
- [x] Unit tests for all levels (73 tests passing)

### Phase 3 (Complete ✅)
- [x] Event loop with PostgreSQL polling (`src/core/engine.py`)
- [x] Agent shell with LLM execution (`src/core/agent.py`)
- [x] FastMCP tool binding with async safety (`src/core/tools.py`)
- [x] LLM client for OpenAI/Anthropic (`src/core/llm_client.py`)
- [x] State resolution & graph progression (Stage 3.4)
- [x] Integration tests (9 tests passing)

## Usage

### Creating and Executing a Workflow

```python
import asyncio
from asyncpg import create_pool
from src.pipeline.validation import ValidationPipeline
from src.models.prompt_contract import PromptContract

async def main():
    # 1. Create database pool
    pool = await create_pool("postgresql://user:pass@localhost/painpoint")
    
    # 2. Create pipeline
    pipeline = ValidationPipeline(pool)
    
    # 3. Create workflow
    workflow_id = await pipeline.save_workflow("My Workflow")
    
    # 4. LLM generates contract (simulated)
    llm_output = '''{
        "role": "data_scraper",
        "constraints": ["rate_limit: 100/day"],
        "allowed_tools": ["mcp_erpnext_read"],
        "decision_rules": {"success": "next_node"},
        "max_retries": 1
    }'''
    
    # 5. Validate and save (Phase 2)
    node_id, status = await pipeline.compile_and_save_contract(
        llm_output, workflow_id
    )
    print(f"Node {node_id} created with status: {status}")
    
    # 6. Phase 3 engine picks up PENDING nodes and executes
    # (Run core/engine.py orchestration_loop)

asyncio.run(main())
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific phase tests
pytest tests/test_syntax_parser.py -v
pytest tests/test_business_rules.py -v
pytest tests/test_human_gate.py -v

# Integration tests (requires PostgreSQL)
pytest tests/test_pipeline_integration.py -v
```

## Configuration

See `.env.example` for required environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `LLM_API_KEY`: API key for LLM provider
- `LLM_MODEL`: Model name (e.g., "gpt-4")
- `MAX_CONCURRENT_TASKS`: Limit concurrent executions (default: 5)

## Next Steps

1. Complete Phase 3 implementation:
   - `src/core/engine.py` - Event loop
   - `src/core/agent.py` - Agent shell
   - `src/core/tools.py` - Tool registry
2. Add comprehensive integration tests
3. Add monitoring and observability
4. Deploy to 4GB server
