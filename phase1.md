/# PHASE 1: The Relational Core & State Manager
## Objective: Establish the database schema, the Pydantic validation layer (Levels 1 & 2), and the hard-coded State Machine (Level 3).

STAGE 1.1: Immutable Relational Schema
Purpose: Build the physical database structure. No dynamic table generation. All LLM outputs must map into these strict bounds.

Execution Steps
Initialize PostgreSQL Database.

Create Core Tables:

workflows: Tracks the parent execution graph.

nodes: Represents individual executable steps (Agents/Tools). Contains the prompt_contract as a strict JSONB column.

edges: Defines the directed execution path between nodes.

execution_logs: Append-only ledger for Level 5 auditing.

Database Schema (Strict SQL)
SQL
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'DRAFT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL, -- e.g., 'TRIGGER', 'AGENT', 'TOOL'
    prompt_contract JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING'
);

CREATE TABLE edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows(id) ON DELETE CASCADE,
    from_node_id UUID REFERENCES nodes(id),
    to_node_id UUID REFERENCES nodes(id),
    condition_rule JSONB -- e.g., {"if": "output == true"}
);
Stage 1.1 Anti-Slop & Verification
Anti-Slop: We are intentionally omitting ORMs (like SQLAlchemy) in favor of raw async SQL (asyncpg). ORMs on a 4GB VPS consume unnecessary RAM and abstract away query tuning.

Verification: Ensure foreign keys use ON DELETE CASCADE to prevent orphaned nodes, maintaining data integrity without manual garbage collection.

STAGE 1.2: Pydantic Validation Engine (Level 1 & Level 2 Gates)
Purpose: Enforce syntax and semantic checks. The LLM (Level 0) outputs a draft JSON contract. This stage either parses it perfectly or rejects it violently.

Execution Steps
Define the PromptContract Pydantic model.

Implement model_validator to check internal logic (Semantic Validation).

Python Validation Model
Python
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional

class PromptContract(BaseModel):
    role: str = Field(..., min_length=10, max_length=500)
    allowed_tools: List[str] = Field(default_factory=list)
    forbidden_actions: List[str] = Field(default_factory=list)
    max_retries: int = Field(default=3, le=5) # Semantic check: never retry more than 5 times
    
    @model_validator(mode='after')
    def validate_tool_isolation(self):
        # Semantic Validation (Level 2)
        intersection = set(self.allowed_tools) & set(self.forbidden_actions)
        if intersection:
            raise ValueError(f"Contradiction: Tools cannot be both allowed and forbidden. Overlap: {intersection}")
        
        # Business Rule Validation (Level 3 prep)
        if "mcp_database_write" in self.allowed_tools and "human_approval" not in self.allowed_tools:
            raise ValueError("Business Rule Violation: Write access requires human approval tool.")
        return self
Stage 1.2 Anti-Slop & Verification
Anti-Slop: No "fuzzy matching" or "LLM auto-correction" on failed schemas. If the LLM returns invalid JSON, the system catches the ValidationError and forces the LLM to retry with the exact error trace.

Verification: Unit tests must be written specifically to feed malformed, malicious, and logically contradictory JSON into this class to ensure it fails closed.

STAGE 1.3: Hardcoded State Machine (Level 3 Gate)
Purpose: Define the absolute laws of workflow progression. The LLM cannot change the status of a node directly. The execution engine transitions state based on deterministic outcomes.

Execution Steps
Define strict Enum for states.

Build the transition enforcer class.

Valid State Transitions
DRAFT → PENDING (Workflow compiled and locked)

PENDING → RUNNING (Event loop picks it up)

RUNNING → AWAITING_APPROVAL (Level 4 Gate Triggered)

AWAITING_APPROVAL → RUNNING (Human approved) / FAILED (Human rejected)

RUNNING → SUCCESS (Output passes validation)

RUNNING → FAILED (Timeout, exception, or validation failure)

Stage 1.3 Anti-Slop & Verification
Anti-Slop: Do not use a heavy state-machine library. A simple dictionary matrix or match-case statement in Python is lighter and easier to debug.

Verification: If a node in SUCCESS state attempts to transition to RUNNING, the system must throw a fatal IllegalStateTransition error and halt. Re-execution requires resetting the node to PENDING explicitly.

STAGE 1.4: The Write-to-DB Pipeline (Level 5 Checkpoint)
Purpose: Connect Levels 0 through 5 into a single functional loop for saving a workflow.

The Pipeline Logic
Level 0: LLM generates raw string.

Level 1: json.loads(raw_string) -> If fail, reject.

Level 2 & 3: Pass to PromptContract(parsed_json) -> If ValidationError, reject.

Level 4: (N/A for compilation phase, applies during execution).

Level 5: Map valid Pydantic object to nodes.prompt_contract JSONB column. Execute INSERT via asyncpg.

Stage 1.4 Anti-Slop & Verification
Anti-Slop: The database connection only accepts validated Pydantic objects converted via model_dump(). It never accepts raw dictionaries.

Verification: Run an end-to-end integration test: Input mock LLM text -> Pipeline -> Query DB to ensure valid JSONB serialization.
