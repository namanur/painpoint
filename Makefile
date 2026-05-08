# PainPoint Lean Orchestrator — Dev Shortcuts (SQLite Edition)
# Usage: make <target>
#
# First time:   make dev
# Daily use:    make cli / make run / make test

VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

.DEFAULT_GOAL := help

# ── Bootstrap ─────────────────────────────────────────────────────────────────

.PHONY: dev
dev: ## One-command setup (first time or after a pull)
	@bash setup.sh

# ── Daily use ─────────────────────────────────────────────────────────────────

.PHONY: cli
cli: _venv_check ## Open the brain-dump intake terminal (SQLite only)
	$(PYTHON) -m local_cli

.PHONY: run
run: _venv_check ## Start the Phase 3 execution engine (uses PAINPOINT_DATABASE_URL)
	$(PYTHON) -m src.main run

.PHONY: api
api: _venv_check ## Start the Phase 4 API server (localhost:8000)
	$(PYTHON) -m src.main api

.PHONY: validate
validate: _venv_check ## Run the Phase 2 validation smoke-test
	$(PYTHON) -m src.main validate

# ── Testing ───────────────────────────────────────────────────────────────────

.PHONY: test
test: _venv_check ## Run all unit tests (no DB required)
	$(VENV)/bin/pytest tests/test_prompt_contract.py \
	                   tests/test_state_machine.py \
	                   tests/test_syntax_parser.py \
	                   tests/test_business_rules.py \
	                   tests/test_human_gate.py \
	                   tests/test_local_cli.py \
	                   -v

.PHONY: test-all
test-all: _venv_check ## Run all tests including DB integration tests
	$(VENV)/bin/pytest tests/ -v

.PHONY: test-fast
test-fast: _venv_check ## Run tests, stop on first failure
	$(VENV)/bin/pytest tests/test_prompt_contract.py \
	                   tests/test_state_machine.py \
	                   tests/test_syntax_parser.py \
	                   -x -q

# ── DB helpers ────────────────────────────────────────────────────────────────

.PHONY: db-setup
db-setup: _venv_check ## Initialize SQLite schema
	$(PYTHON) -m src.main setup

.PHONY: db-reset
db-reset: ## Delete and recreate the SQLite database (destructive!)
	@echo "Resetting SQLite database 'painpoint.db'..."
	@rm -f painpoint.db
	$(PYTHON) -m src.main setup
	@echo "Done."

# ── Deps ──────────────────────────────────────────────────────────────────────

.PHONY: install
install: _venv_check ## Re-install/update dependencies
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements.txt

.PHONY: install-llm
install-llm: _venv_check ## Install optional LLM clients (anthropic, openai)
	$(PIP) install anthropic openai

# ── Housekeeping ──────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove .venv, __pycache__, sessions/
	rm -rf $(VENV) __pycache__ src/__pycache__ .pytest_cache
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."

.PHONY: sessions-clean
sessions-clean: ## Delete all saved plan files in sessions/
	rm -f sessions/plan_*.md
	@echo "Sessions cleared."

# ── Internal ──────────────────────────────────────────────────────────────────

.PHONY: _venv_check
_venv_check:
	@test -d $(VENV) || (echo "Run 'make dev' first to set up the environment." && exit 1)

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@echo ""
	@echo "  PainPoint — Dev Commands (SQLite)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	    | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
