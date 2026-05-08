**STATE 2 — EXECUTION**

---

# PHASE 3: The Async Execution Engine

**Objective:** Build the single-process, low-overhead runtime. This engine is blind to human intent; it only reads validated `PromptContract` JSONs from the PostgreSQL database and executes them. It does not think. It complies.

## STAGE 3.1: The Event Loop & Database Polling

**Purpose:** Fetch `PENDING` nodes from the database without race conditions and feed them into the execution thread.

### Execution Steps

1. Initialize the `asyncio` event loop.
2. Query the `nodes` table for `PENDING` tasks using `asyncpg`.
3. Atomic lock: Update the node to `RUNNING` immediately upon fetch to prevent double-execution.

### The Loop (`core/engine.py`)

```python
import asyncio
from core.db import get_pool # asyncpg pool
from core.agent import execute_node

async def orchestration_loop():
    pool = await get_pool()
    while True:
        async with pool.acquire() as conn:
            # Atomic fetch-and-lock to prevent race conditions
            record = await conn.fetchrow("""
                UPDATE nodes
                SET status = 'RUNNING'
                WHERE id = (
                    SELECT id FROM nodes
                    WHERE status = 'PENDING'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, workflow_id, prompt_contract;
            """)

            if record:
                # Fire and forget task to keep loop unblocked
                asyncio.create_task(execute_node(record['id'], record['prompt_contract']))
            else:
                # Throttle when idle to save CPU on the 4GB server
                await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(orchestration_loop())

```

### Stage 3.1 Anti-Slop & Verification

* **Anti-Slop:** Do not use Celery, Redis queues, or RabbitMQ for this. You are on a 4GB machine. PostgreSQL `FOR UPDATE SKIP LOCKED` acts as a perfectly stable, zero-dependency message queue for a solo operator.
* **Verification:** Spin up two instances of the loop locally pointing to the same DB. Insert 10 `PENDING` nodes. Verify that no node is executed twice.

---

## STAGE 3.2: The Base Agent Class (The Shell)

**Purpose:** A static Python class that hydrates its behavior entirely from the `PromptContract`. It has no innate logic other than how to talk to the LLM API.

### Execution Steps

1. Parse the `PromptContract` back into a Pydantic object.
2. Construct the system prompt strictly from the contract's parameters.
3. Execute the LLM call.

### The Agent Shell (`core/agent.py`)

```python
import json
from core.models import PromptContract
# Assuming a generic async LLM client (e.g., async openai or litellm)
from core.llm_client import async_llm_call

async def execute_node(node_id: str, contract_json: str):
    contract = PromptContract.model_validate_json(contract_json)

    system_prompt = f"""
    You are an agent with the following role: {contract.role}.
    You must obey these constraints: {json.dumps(contract.constraints)}.
    If you reach a decision, output your routing choice based on these rules: {json.dumps(contract.decision_rules)}.
    """

    retries = 0
    while retries < contract.max_retries:
        try:
            # Stage 3.3 FastMCP integration happens inside this call
            response = await async_llm_call(
                system_prompt=system_prompt,
                allowed_tools=contract.allowed_tools
            )
            await mark_success(node_id, response)
            return
        except Exception as e:
            retries += 1
            await log_execution(node_id, str(e), status="RETRYING")

    await mark_failed(node_id, "Max retries exceeded.")

```

### Stage 3.2 Anti-Slop & Verification

* **Anti-Slop:** Do not import LangChain or LlamaIndex. They abstract the prompt construction in ways that break determinism. You must control the exact string passed to the API.
* **Verification:** Pass a contract with `max_retries: 1` and a forced API failure. Verify the system marks it `FAILED` exactly after one attempt, not infinite looping.

---

## STAGE 3.3: FastMCP Tool Binding

**Purpose:** Attach tools to the LLM securely. FastMCP provides the interface, but the execution must respect the single-process event loop.

### Execution Steps

1. Define tools in a central registry.
2. Map the `allowed_tools` array from the contract to the registered functions.
3. **Crucial:** Wrap synchronous I/O.

### Tool Execution Standard (`core/tools.py`)

```python
import asyncio
import requests
from fastmcp import FastMCP

mcp = FastMCP("LeanOrchestrator")

# Example of a DANGEROUS sync function wrapped properly
def _sync_scrape_erpnext(endpoint: str):
    # This blocks. If run raw, the whole orchestrator freezes.
    return requests.get(endpoint).json()

@mcp.tool()
async def mcp_erpnext_read(endpoint: str) -> str:
    """Reads data from ERPNext."""
    try:
        # Offload the blocking sync call to a background thread
        result = await asyncio.to_thread(_sync_scrape_erpnext, endpoint)
        return str(result)
    except Exception as e:
        return f"Tool execution failed: {e}"

```

### Stage 3.3 Anti-Slop & Verification

* **Anti-Slop:** Never assume a third-party library is async-safe. If it uses `requests`, `urllib`, or standard file `open()`, it will hang your entire orchestration loop. Wrap it in `asyncio.to_thread()`.
* **Verification:** Write a tool with `time.sleep(5)`. Call it via the agent. Verify that the main `orchestration_loop()` continues to poll the database during those 5 seconds. If polling stops, your loop is blocked and the architecture is broken.

---

## STAGE 3.4: State Resolution & Graph Progression

**Purpose:** Handle the output of the agent, write the audit log, and trigger the next node in the workflow graph based on the `decision_rules`.

### Execution Steps

1. Write the raw output to `execution_logs` (Level 5 Checkpoint).
2. Update current node to `SUCCESS`.
3. Query the `edges` table using the `decision_rules` outcome to find the `to_node_id`.
4. Update the next node from `DRAFT` to `PENDING`.

### Stage 3.4 Anti-Slop & Verification

* **Anti-Slop:** Graph progression must be handled by the backend routing logic, not the LLM. The LLM outputs a structured decision (e.g., `{"route": "node_4"}`). The database code executes the SQL `UPDATE` to transition the state. The LLM is never allowed to directly mutate table states.
* **Verification:** Run a two-node workflow. Node A completes successfully. Query the DB to ensure Node A is `SUCCESS`, the transition log exists in `execution_logs`, and Node B is now `PENDING`.
