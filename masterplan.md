**STATE 0 — INPUT CLASSIFICATION**

Project Count: 1 (Lean Agent Orchestrator Context Document)
Problem vs. Solution: Solution compilation for LLM context grounding.
Type: Architecture Documentation / Masterplan Build.
Existing System: Consolidating previously established constraints.
Operator: Solo automation.
Classification: Operational foundation.

**PROJECT FINGERPRINT**
Type: new build
Operator: solo automation
Problem Clarity: defined
Existing System: no
Emotional Signal Strength: low
Execution Value: high
Proceed To: STATE 2

---

**STATE 2 — EXECUTION**

This is the consolidated Master Architecture Payload. Use this document as the system prompt or knowledge base for any LLM working on this project to ensure strict adherence to the established boundaries. Boring systems survive.

---

# MASTER ARCHITECTURE PAYLOAD: LEAN AGENT ORCHESTRATOR

### 4. BRD / North Star (Context Grounding)

* **Problem:** Enterprise orchestrators (e.g., Paperclip) rely on high-overhead visual control planes, multi-container heartbeats, and dynamic schemas that crush a 4GB RAM VPS. Solo operators need deterministic execution, not Kubernetes theater.
* **Value:** A single-process, async-driven orchestrator that translates plain-English intent into visual graphs (Mermaid) and strict, executable JSON "Prompt Contracts."
* **Core Law:** The LLM suggests; the code decides. Prompt Contracts are immutable during execution. Dynamic schema mutation is forbidden.

---

### 3. System Architecture & Tool Map

* **Target Hardware:** 4GB RAM Ubuntu Server.
* **Execution Model:** Single-process `asyncio` event loop.
* **Database:** PostgreSQL (Relational core for state/routing + `JSONB` for Prompt Contracts and execution metadata).
* **Tool Bindings:** `FastMCP` (Model Context Protocol) for lightweight, isolated tool execution.
* **Validation Layer:** Pydantic (Strict schema enforcement).
* **Visual Representation:** Mermaid.js generated from JSON (No drag-and-drop state mutation; edits require regeneration through the compiler).

---

### 1. Build Order (The Phases)

#### **PHASE 1: The Relational Core & State Manager**

*The immutable ground truth. No dynamic table generation allowed.*

* **1.1 Fixed PostgreSQL Schema:**
* `workflows` (ID, Name, Status)
* `nodes` (ID, Workflow_ID, Type, `prompt_contract` [JSONB], Status)
* `edges` (ID, From_Node, To_Node, Condition_Rule [JSONB])
* `execution_logs` (Append-only ledger, segregated from state to prevent JSONB bloat).


* **1.2 State Machine Enforcement:**
* Hardcoded transitions only (e.g., `PENDING` → `RUNNING` → `SUCCESS` / `FAILED`).
* Illegal transitions throw fatal backend errors.



#### **PHASE 2: The 5-Level Validation Pipeline**

*The defensive wall against LLM hallucination and Prompt Contract poisoning.*

* **Level 0 - Raw Generation (Untrusted):** LLM outputs a draft JSON contract. No execution allowed.
* **Level 1 - Syntax Validation (Pydantic):** Is it perfectly formatted JSON matching the `PromptContract` schema? Failure = instant rejection.
* **Level 2 - Semantic Validation (Pydantic `model_validator`):** Does the logic hold? (e.g., `allowed_tools` and `forbidden_actions` cannot intersect. `max_retries` cannot exceed 5).
* **Level 3 - Business Rule Validation (Hardcoded):** Does this violate operational reality? (e.g., Write-access tools require the human-approval tool).
* **Level 4 - Human Approval Gate:** Triggered automatically for high-risk tools (money movement, database drops). AI proposes, human approves.
* **Level 5 - Execution Layer:** The validated Prompt Contract is saved to PostgreSQL and queued for the `asyncio` loop.

#### **PHASE 3: The Async Execution Engine**

*The runtime environment. Optimized for low overhead.*

* **3.1 Single-Process Loop:** Python `asyncio` loop pulling `PENDING` nodes from the database.
* **3.2 Base Agent Class:** A static Python class that hydrates its behavior dynamically based purely on the `Prompt Contract` fetched from the DB.
* **3.3 MCP Integration:** Tools are exposed to the agent strictly via FastMCP. Synchronous third-party API calls must be wrapped in `asyncio.to_thread()` to prevent blocking the single event loop.

#### **PHASE 4: The Compiler & Visual Render Layer**

*The NLP-to-Execution interface.*

* **4.1 Tri-Phase Extraction Protocol:** Guided Q&A (Boundary Definition → Logic Branching → Resource Mapping) to extract operational intent.
* **4.2 GUI Rendering:** LLM translates the validated workflow matrix into a Mermaid.js flowchart.
* **4.3 Controlled Mutation:** Users click nodes to inspect logic. They cannot arbitrarily drag arrows to change execution state. They edit the prompt constraints or tool rules, which passes back through the 5-Level Validation Pipeline to generate a new, safe Prompt Contract.

---

### 2. Failure Map & Security Risks

| Risk Area | Vulnerability | Hardcoded Mitigation |
| --- | --- | --- |
| **Execution Blockage** | A synchronous API call in an agent tool hangs, blocking the single 4GB RAM event loop. | Strict `aiohttp` usage; all legacy sync calls wrapped in `asyncio.to_thread()`. |
| **Logic Poisoning** | LLM hallucinates a tool name or rewrites its own `forbidden_actions` array. | Level 1 & 2 Validation. Pydantic drops the payload if tools aren't in the pre-approved enum. |
| **Database Bloat** | Storing verbose LLM reasoning and HTML scrape data in the `nodes` JSONB column. | Segregate state from logs. `nodes` only stores the Prompt Contract. `execution_logs` handles the garbage and is pruned chronologically. |
| **Schema Drift** | LLM attempts to execute DDL (CREATE/ALTER TABLE) to accommodate a new workflow type. | Database user assigned to the orchestrator has `INSERT/UPDATE/SELECT` privileges only. DDL is revoked. |

---

### 5. Deterministic Next Actions

1. **Initialize Infrastructure:** Boot the Python 3.11+ environment, configure `asyncpg` connection pools, and execute the static `CREATE TABLE` DDL for the PostgreSQL core.
2. **Lock the Data Model:** Write the Pydantic `PromptContract` model, including all Level 1 (type) and Level 2 (semantic intersection) validators. Write unit tests passing malformed JSON to guarantee failure.
3. **Draft the Engine Core:** Write the skeletal `asyncio` loop that reads a hardcoded, valid `Prompt Contract` from the database and executes a single dummy FastMCP tool.
