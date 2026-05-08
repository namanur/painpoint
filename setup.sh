#!/usr/bin/env bash
# =============================================================================
# PainPoint Lean Orchestrator — One-Command Dev Setup (SQLite Edition)
# Usage: ./setup.sh
# =============================================================================
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }
step() { echo -e "\n${BOLD}$1${NC}"; }

echo -e "${BOLD}"
echo "  ┌──────────────────────────────────────┐"
echo "  │  PainPoint — Dev Setup (SQLite)      │"
echo "  │  One command. Done.                  │"
echo "  └──────────────────────────────────────┘"
echo -e "${NC}"

# ── 1. Python version ────────────────────────────────────────────────────────
step "[1/5] Checking Python"

PYTHON=$(command -v python3 || command -v python || true)
[ -z "$PYTHON" ] && fail "Python 3.10+ not found. Install from https://python.org"

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

[ "$PY_MAJOR" -lt 3 ] && fail "Python 3.10+ required (found $PY_VERSION)"
[ "$PY_MINOR" -lt 10 ] && fail "Python 3.10+ required (found $PY_VERSION)"
ok "Python $PY_VERSION"

# ── 2. Virtual environment ───────────────────────────────────────────────────
step "[2/5] Virtual environment"

if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
    ok "Created .venv"
else
    ok ".venv already exists — skipping"
fi

# Activate
source .venv/bin/activate
PYTHON=python  # now points to venv python

# ── 3. Dependencies ──────────────────────────────────────────────────────────
step "[3/5] Installing dependencies"

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Optional LLM extras — don't fail if missing
pip install --quiet anthropic openai 2>/dev/null && ok "LLM clients (anthropic, openai)" \
    || warn "anthropic/openai not installed — CLI will use mock LLM"

ok "All dependencies installed"

# ── 4. Environment file ──────────────────────────────────────────────────────
step "[4/5] Environment config"

if [ ! -f ".env" ]; then
    cp .env.example .env
    ok "Created .env from .env.example"
else
    ok ".env already exists — skipping"
fi

# ── 5. Database Setup (SQLite) ───────────────────────────────────────────────
step "[5/5] Database Setup (SQLite)"

# Run schema initialization via src.main
python -m src.main setup && ok "SQLite database initialized (painpoint.db)" \
    || fail "Database initialization failed"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  Setup complete!${NC}"
echo ""

echo -e "  ${BOLD}Try it now:${NC}"
echo -e "  ${DIM}source .venv/bin/activate${NC}"
echo -e "  ${DIM}python -m local_cli          # brain-dump → plan${NC}"
echo -e "  ${DIM}python -m src.main run       # start execution engine${NC}"
echo -e "  ${DIM}python -m src.main api       # start API server${NC}"

echo -e "\n  ${DIM}Re-run this script anytime to update dependencies.${NC}\n"
