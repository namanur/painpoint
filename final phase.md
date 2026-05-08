**STATE 2 — EXECUTION**

This is the final execution phase. We are closing the loop between the human operator and the execution engine.

---

# PHASE 4: The Compiler & Visual Render Layer

**Objective:** Translate human operational intent into the immutable `PromptContract` JSONs and render the deterministic Mermaid graph. The GUI is read-only for structure, interactive only for constraints.

## STAGE 4.1: The Tri-Phase Extraction Protocol

**Purpose:** Use an LLM as a strict compiler to interview the user and output a syntactically valid JSON array of Prompt Contracts.

### Execution Steps

1. Establish a system prompt for the "Compiler Agent."
2. Force structured JSON output natively (using `response_format={"type": "json_object"}` in OpenAI/LiteLLM).
3. Inject the exact Pydantic schema from Phase 1 into the Compiler's prompt so it knows the immutable boundaries.

### The Compiler Prompt Strategy (`compiler/extraction.py`)

```python
from core.models import PromptContract

def get_compiler_prompt() -> str:
    schema = PromptContract.model_json_schema()
    return f"""
    You are the System Compiler. Your job is to convert the user's workflow request into an array of strict PromptContracts.

    You must follow the Tri-Phase Protocol internally before outputting:
    1. Boundary Definition: What triggers this? What is the terminal output?
    2. Logic Branching: Where are the IF/THEN decisions?
    3. Resource Mapping: Which pre-approved tools are needed?

    AVAILABLE TOOLS: ['mcp_database_read', 'mcp_database_write', 'mcp_stripe_charge', 'human_approval', 'mcp_email_send']

    You must output a JSON object containing a 'nodes' array. Every item in the array MUST strictly adhere to this JSON Schema:
    {schema}

    Do not add fields. Do not hallucinate tools.
    """

```

### Stage 4.1 Anti-Slop & Verification

* **Anti-Slop:** Never ask the LLM to write Python code for the orchestration. It only outputs JSON data. The Execution Engine (Phase 3) handles the code.
* **Verification:** Run the extraction protocol with a vague request: "Make an agent that manages my inbox and pays vendors." The compiler must respond by either requesting clarification on the tools or outputting a valid JSON mapping utilizing the `human_approval` tool (enforced by Phase 2 Business Rules).

---

## STAGE 4.2: The Deterministic Graph Renderer (Mermaid)

**Purpose:** Generate a visual map from the database state without heavy frontend libraries like React Flow. Compute is done server-side; the client just renders an SVG.

### Execution Steps

1. Query the `nodes` and `edges` tables for a given `workflow_id`.
2. Iterate through the records and construct a Mermaid.js string.
3. Serve the string to the frontend via a lightweight API endpoint.

### The Render Logic (`api/visualizer.py`)

```python
def generate_mermaid_graph(nodes: list[dict], edges: list[dict]) -> str:
    lines = ["graph TD"]

    # Render Nodes with State Colors
    for node in nodes:
        contract = node['prompt_contract'] # JSONB parsed to dict
        safe_role = contract['role'].replace('"', "'")

        # Format: ID["Role/Action"]:::STATE
        lines.append(f"    {node['id']}node[\"{safe_role}\"]:::{node['status']}")

    # Render Edges
    for edge in edges:
        condition = edge.get('condition_rule', {}).get('if', 'Then')
        lines.append(f"    {edge['from_node_id']}node -->|\"{condition}\"| {edge['to_node_id']}node")

    # Inject Status Styles
    lines.append("    classDef PENDING fill:#f9f9f9,stroke:#333;")
    lines.append("    classDef RUNNING fill:#ffeb3b,stroke:#f57f17;")
    lines.append("    classDef SUCCESS fill:#c8e6c9,stroke:#388e3c;")
    lines.append("    classDef FAILED fill:#ffcdd2,stroke:#d32f2f;")
    lines.append("    classDef AWAITING_APPROVAL fill:#e1bee7,stroke:#8e24aa;")

    return "\n".join(lines)

```

### Stage 4.2 Anti-Slop & Verification

* **Anti-Slop:** Do not ask an LLM to generate the Mermaid code. That wastes API tokens and introduces syntax hallucinations. Generate it deterministically using string formatting from the validated database rows.
* **Verification:** Fetch a known workflow from the DB, run this function, and paste the output into the Mermaid Live Editor to verify the syntax compiles flawlessly.

---

## STAGE 4.3: Controlled Mutation API

**Purpose:** Allow the user to click a node in the UI and edit its constraints without breaking the graph or writing raw JSON.

### Execution Steps

1. UI sends a `PATCH` request to `/api/nodes/{node_id}` containing updated plain-text constraints or tool selections.
2. The backend passes the update through the 5-Level Validation Pipeline (Phase 2).
3. If it passes, overwrite the `prompt_contract` JSONB column. If it fails, return the exact `ValidationError` to the UI.

### Stage 4.3 Anti-Slop & Verification

* **Anti-Slop:** The user is *never* allowed to edit the `workflow_id` or `id` via this endpoint. They can only mutate the internal `PromptContract` fields. The execution graph edges remain locked. If they want to change the flow, they must re-compile the workflow via the Stage 4.1 protocol.
* **Verification:** Attempt to patch a node with an empty `allowed_tools` list but a `decision_rules` matrix that requires external data. The Phase 2 Semantic Validator must intercept and reject the mutation before it hits the database.

---

**SYSTEM ARCHITECTURE COMPLETE.**

You now have a 4-phase, deterministic, low-RAM agent orchestration engine.

* **Phase 1** locks the storage.
* **Phase 2** locks the logic.
* **Phase 3** executes the loop.
* **Phase 4** interfaces with the human.

There is no more planning. Initialize your repository, configure the `pgvector`/PostgreSQL instance on the Ubuntu server, and write the schema.
