**STATE 2 — EXECUTION**

---

# PHASE 2: The 5-Level Validation Pipeline

**Objective:** Construct the immutable logic gauntlet. This pipeline converts untrusted, raw LLM output (Level 0) into a guaranteed, executable `PromptContract`. If an output fails any gate, it is rejected entirely.

## STAGE 2.1: Level 1 & Level 2 Gate (Syntax & Semantic Parsing)

**Purpose:** Ensure the raw output is syntactically valid JSON and passes intrinsic semantic logic via Pydantic before it ever touches business logic.

### Execution Steps

1. Isolate the raw generation call (Level 0) from the parsing logic.
2. Attempt `json.loads()`. Catch `json.JSONDecodeError` immediately.
3. Pass the parsed dictionary to the `PromptContract` Pydantic model (defined in Phase 1).

### The Parsing Module (`validators/syntax_parser.py`)

```python
import json
from pydantic import ValidationError
from core.models import PromptContract # From Phase 1

class CompilationError(Exception):
    pass

def run_level_1_and_2(raw_llm_output: str) -> PromptContract:
    try:
        # Strip potential markdown code blocks from LLM response
        clean_json_str = raw_llm_output.strip().removeprefix("```json").removesuffix("
```").strip()
        
        # Level 1: Syntax
        raw_dict = json.loads(clean_json_str)
        
        # Level 2: Semantic (Pydantic model validation runs here)
        contract = PromptContract(**raw_dict)
        return contract
        
    except json.JSONDecodeError as e:
        raise CompilationError(f"Level 1 Failure: Invalid JSON syntax. Details: {e}")
    except ValidationError as e:
        raise CompilationError(f"Level 2 Failure: Semantic validation failed. Details: {e}")

```

### Stage 2.1 Anti-Slop & Verification

* **Anti-Slop:** Never use an LLM "auto-fix" library (like `guardrails` or `instructor` with infinite retry loops) on the backend. If it fails, throw the `CompilationError` to the orchestration layer. The orchestrator can decide to append the error trace to the prompt and retry *once*, or fail the compilation job.
* **Verification:** Unit tests must feed stringified Python dictionaries (invalid JSON), truncated JSON strings, and JSON with missing required Pydantic fields. All must trigger `CompilationError`.

---

## STAGE 2.2: Level 3 Gate (Business Rule Engine)

**Purpose:** Enforce operational reality that a schema validator cannot know. This connects the isolated contract to external system realities.

### Execution Steps

1. Define a dictionary or registry of hardcoded business rules.
2. Pass the valid `PromptContract` through the rule engine before it is allowed to be saved.

### The Rule Engine (`validators/business_rules.py`)

```python
from core.models import PromptContract

class BusinessRuleViolation(Exception):
    pass

def enforce_level_3(contract: PromptContract, existing_workflows: list[str] = None):
    # Rule 1: High-risk tools require specific isolation
    dangerous_tools = {"mcp_database_write", "mcp_stripe_charge"}
    requested_danger = set(contract.allowed_tools).intersection(dangerous_tools)
    
    if requested_danger and "human_approval" not in contract.allowed_tools:
        raise BusinessRuleViolation(
            f"Level 3 Failure: Tools {requested_danger} require 'human_approval' in allowed_tools."
        )

    # Rule 2: Execution time limits based on role
    if "scraper" in contract.role.lower() and contract.max_retries > 1:
         raise BusinessRuleViolation(
            "Level 3 Failure: Scraper roles are strictly limited to 1 retry to prevent infinite hanging."
        )
         
    return contract

```

### Stage 2.2 Anti-Slop & Verification

* **Anti-Slop:** The LLM is completely blind to this file. Do not inject business rules into the LLM prompt hoping it will obey them. The code enforces the law.
* **Verification:** Pass a perfectly valid Pydantic `PromptContract` object that requests `mcp_database_write` but forgets `human_approval`. It must crash with `BusinessRuleViolation`.

---

## STAGE 2.3: Level 4 Gate (The Human Approval Checkpoint)

**Purpose:** Identify if the validated contract requires human intervention before transitioning to the `RUNNING` state in the database.

### Execution Steps

1. Analyze the contract for trigger conditions.
2. Return a boolean flag to the pipeline integrator.

### The Checkpoint Logic (`validators/human_gate.py`)

```python
from core.models import PromptContract

def requires_level_4_approval(contract: PromptContract) -> bool:
    approval_triggers = ["mcp_stripe_charge", "mcp_database_drop", "mcp_email_send"]
    
    if any(tool in contract.allowed_tools for tool in approval_triggers):
        return True
    return False

```

### Stage 2.3 Anti-Slop & Verification

* **Anti-Slop:** This does not pause the thread. Waiting for human input on a live async thread will crash the single-process 4GB server. This function simply flags the database insert to mark the node as `AWAITING_APPROVAL` instead of `PENDING`.
* **Verification:** Test that tools outside the trigger list return `False` and tools inside return `True`.

---

## STAGE 2.4: The Pipeline Integrator (Level 0 → Level 5)

**Purpose:** The single entry point that orchestrates the gates and executes the Level 5 database transaction.

### Execution Steps

1. Receive raw LLM string.
2. Pass through Levels 1, 2, 3.
3. Check Level 4.
4. Execute Level 5 (Database Insert).

### The Integrator (`core/pipeline.py`)

```python
from validators.syntax_parser import run_level_1_and_2
from validators.business_rules import enforce_level_3
from validators.human_gate import requires_level_4_approval
# Assume db_insert_node is an async function from Phase 1 DB logic

async def compile_and_save_contract(raw_llm_output: str, workflow_id: str):
    # Gates 1 & 2
    contract = run_level_1_and_2(raw_llm_output)
    
    # Gate 3
    contract = enforce_level_3(contract)
    
    # Gate 4 Check
    needs_approval = requires_level_4_approval(contract)
    initial_state = "AWAITING_APPROVAL" if needs_approval else "PENDING"
    
    # Gate 5 (Execution to DB)
    node_id = await db_insert_node(
        workflow_id=workflow_id,
        contract_json=contract.model_dump_json(),
        status=initial_state
    )
    
    return node_id, initial_state

```

### Stage 2.4 Anti-Slop & Verification

* **Anti-Slop:** This function is strictly linear. There are no circular dependencies, no "agentic reasoning" loops. Data goes in, runs the gauntlet, and either dies via Exception or lands in PostgreSQL.
* **Verification:** Integration test. Mock an LLM response containing a dangerous tool. Assert that the function successfully inserts the row into PostgreSQL and that the returned state is strictly `AWAITING_APPROVAL`.

```

```
