# PainPoint: Lean Agent Orchestrator

**PainPoint** is a deterministic, single-process orchestration engine designed for high-velocity agent execution in 4GB RAM environments. It prioritizes "Anti-Slop" principles: avoiding heavyweight frameworks (like LangChain), maintaining exact string control for LLM prompts, and using the database as a robust message queue.

## 🏗 Project Architecture

The project follows a phased evolution model:

- **Phase 1: Relational Core:** PostgreSQL/SQLite database schema and state management.
- **Phase 2: Validation Pipeline:** Strict contract enforcement via Pydantic (`PromptContract`).
- **Phase 3: Execution Engine:** Asyncio-based polling loop that dispatches agent tasks.
- **Phase 4: API & Visualization:** FastAPI server for management and real-time visualization.

### Key Components

- **Project Genesis (CLI):** Located in `local_cli/`, it provides the "Glass Window" terminal for frictionless workflow intake using native text editors.
- **The Engine:** Located in `src/core/engine.py`, it implements the main orchestration loop.
- **The Agent:** Located in `src/core/agent.py`, it hydrates behavior entirely from contracts and manages LLM interaction.
- **Explicit DAO Layer:** Located in `src/db/schema.py`, it provides database-specific implementations for PostgreSQL (high concurrency) and SQLite (development/single process).

## 🚀 Commands & Usage

### Setup & Installation
- `make dev`: One-step setup (runs `setup.sh`, creates venv, installs dependencies).
- `make db-setup`: Initializes the SQLite schema.

### Running the System
- `make cli`: Opens the interactive intake terminal (Project Genesis).
- `make run`: Starts the Phase 3 execution engine (polls the DB for nodes).
- `make api`: Starts the Phase 4 API server (localhost:8000).

### Development & Testing
- `make test`: Runs standard unit tests.
- `make test-all`: Runs all tests including database integration tests.
- `make validate`: Runs the Phase 2 validation smoke-test.
- `make db-reset`: Destructive reset of the SQLite database.

## 🛠 Development Conventions

### The "Anti-Slop" Doctrine
- **No Heavy Frameworks:** Do not introduce LangChain, LlamaIndex, or similar abstractions.
- **Deterministic State:** Use the `src/state/machine.py` for all node status transitions.
- **Exact Prompting:** Maintain absolute control over strings sent to LLM APIs.
- **Database as Queue:** Do not use Celery or Redis. Use `fetch_pending_node` (PostgreSQL `SKIP LOCKED` or SQLite `UPDATE...RETURNING`).

### Coding Standards
- **Prompt Contracts:** Every agent action must be defined by a `PromptContract` in `src/models/prompt_contract.py`.
- **Explicit DAOs:** Never mutate SQL strings at runtime or use regex-based query generation. Add methods to `BaseNodeDAO` in `src/db/schema.py` and implement them for both PostgreSQL and SQLite.
- **Async First:** Use `asyncio` for all I/O bound operations (DB, LLM, API).
- **Environment Config:** Use `src/config.py` for settings. Variables are prefixed with `PAINPOINT_`.

## 📂 Directory Map

- `local_cli/`: The "Glass Window" intake terminal.
- `src/api/`: FastAPI routes and visualizer logic.
- `src/compiler/`: Logic for converting messy intake dumps into structured plans.
- `src/core/`: The "Brain" - engine, agent shell, and tool bindings.
- `src/db/`: Database schema, migrations, and DAO implementations.
- `src/models/`: Pydantic models and prompt contracts.
- `src/state/`: Finite State Machine for workflow/node lifecycles.
- `src/validators/`: Multi-level validation (Syntax, Business Rules, Human Gate).
- `tests/`: Comprehensive test suite.
