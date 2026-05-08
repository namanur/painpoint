# Lean Agent Orchestrator

A single-process, async-driven orchestrator that translates plain-English intent into visual graphs (Mermaid) and strict, executable JSON "Prompt Contracts."

> **Contrast with Paperclip:** While [Paperclip](https://github.com/paperclipai/paperclip) uses 60+ tables with Drizzle ORM, React UI, and multi-container heartbeats (crushing a 4GB RAM VPS), this Lean Orchestrator uses just **4 tables** with raw `asyncpg`, no visual control plane, and a single `asyncio` event loop.

## Architecture Principles

- **Single-process:** One `asyncio` event loop, no Kubernetes theater
- **Immutable contracts:** Prompt Contracts are validated once, then frozen
- **Lean stack:** PostgreSQL + `asyncpg` + Pydantic (no ORM overhead)
- **5-Level Validation:** LLM suggests; code decides

## Phase 1: The Relational Core & State Manager

### Completed Components

| Component | File | Description |
|-----------|------|-------------|
| **Schema** | `src/db/schema.py` | 4 immutable tables (workflows, nodes, edges, execution_logs) |
| **PromptContract** | `src/models/prompt_contract.py` | Pydantic model with Levels 1-3 validation |
| **State Machine** | `src/state/machine.py` | Hardcoded transitions (no library overhead) |
| **Pipeline** | `src/pipeline/validation.py` | Level 0→1→2→3→5 checkpoint pipeline |

### Database Schema

```sql
workflows (id, name, status, created_at)
nodes (id, workflow_id, type, prompt_contract JSONB, status)
edges (id, workflow_id, from_node_id, to_node_id, condition_rule JSONB)
execution_logs (id, node_id, workflow_id, level, message, created_at)
```

### State Transitions

```
DRAFT → PENDING → RUNNING → SUCCESS/FAILED
                  ↓
           AWAITING_APPROVAL (Level 4 gate)
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup PostgreSQL

```bash
# Create database
createdb painpoint

# Copy and configure environment
cp .env.example .env
# Edit .env with your database URL
```

### 3. Run Phase 1 Setup

```bash
python -m src.main
```

### 4. Run Tests

```bash
# Unit tests (no database required)
pytest tests/test_prompt_contract.py tests/test_state_machine.py -v

# Integration tests (requires PostgreSQL)
pytest tests/test_pipeline_integration.py -v
```

## Validation Pipeline

```
Level 0: LLM generates raw JSON string
    ↓
Level 1: JSON syntax validation (json.loads)
    ↓
Level 2: Pydantic schema validation + semantic checks
    ↓
Level 3: Business rule validation (write requires approval)
    ↓
Level 4: Human approval gate (for high-risk tools)
    ↓
Level 5: Save to PostgreSQL JSONB column
```

## Project Structure

```
painpoint/
├── src/
│   ├── __init__.py
│   ├── config.py              # Settings from environment
│   ├── main.py                # Entry point
│   ├── db/
│   │   ├── __init__.py
│   │   └── schema.py          # PostgreSQL schema + pool
│   ├── models/
│   │   ├── __init__.py
│   │   └── prompt_contract.py # PromptContract Pydantic model
│   ├── state/
│   │   ├── __init__.py
│   │   └── machine.py        # Hardcoded state machine
│   └── pipeline/
│       ├── __init__.py
│       └── validation.py     # Level 0-5 pipeline
├── tests/
│   ├── test_prompt_contract.py
│   ├── test_state_machine.py
│   └── test_pipeline_integration.py
├── masterplan.md
├── phase1.md
├── requirements.txt
├── .env.example
└── README.md
```

## Next Steps (Phase 2)

- [ ] Implement Level 4: Human Approval Gate
- [ ] Build the 5-Level Validation Pipeline service
- [ ] Add approval UI (minimal, not drag-and-drop)

## License

MIT

## Reference

- **Paperclip (Anti-pattern):** https://github.com/paperclipai/paperclip
  - 60+ tables, Drizzle ORM, React UI, heartbeats, multi-container
- **Lean Orchestrator (This project):** 4 tables, raw asyncpg, Mermaid.js, single-process
