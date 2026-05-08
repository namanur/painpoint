#!/usr/bin/env bash
# =============================================================================
# PainPoint Lean Orchestrator — One-Command Dev Setup
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
echo "  │  PainPoint — Dev Setup               │"
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

# ── 5. PostgreSQL ────────────────────────────────────────────────────────────
step "[5/5] PostgreSQL"

if ! command -v psql &>/dev/null; then
    warn "psql not found — skipping database setup"
    warn "Install PostgreSQL to enable persistence:"
    echo -e "  ${DIM}macOS:  brew install postgresql && brew services start postgresql${NC}"
    echo -e "  ${DIM}Ubuntu: sudo apt install postgresql && sudo service postgresql start${NC}"
    DB_READY=false
else
    # Check if postgres is running
    if pg_isready -q 2>/dev/null; then
        # Create DB if it doesn't exist
        if psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw painpoint; then
            ok "Database 'painpoint' already exists"
        else
            createdb painpoint 2>/dev/null && ok "Created database 'painpoint'" \
                || warn "Could not create database (may already exist or need sudo)"
        fi
        # Run schema
        python -m src.main setup 2>/dev/null && ok "Schema initialized" \
            || warn "Schema init skipped (check DB connection in .env)"
        DB_READY=true
    else
        warn "PostgreSQL is not running"
        echo -e "  ${DIM}Start it with: brew services start postgresql  (macOS)${NC}"
        echo -e "  ${DIM}           or: sudo service postgresql start   (Linux)${NC}"
        DB_READY=false
    fi
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  Setup complete!${NC}"
echo ""

if [ "$DB_READY" = true ]; then
    echo -e "  ${BOLD}Try it now:${NC}"
    echo -e "  ${DIM}source .venv/bin/activate${NC}"
    echo -e "  ${DIM}python -m local_cli          # brain-dump → plan${NC}"
    echo -e "  ${DIM}python -m src.main run       # start execution engine${NC}"
    echo -e "  ${DIM}python -m src.main api       # start API server${NC}"
else
    echo -e "  ${BOLD}Database not ready. For DB-free use:${NC}"
    echo -e "  ${DIM}source .venv/bin/activate${NC}"
    echo -e "  ${DIM}python -m local_cli          # works without DB (mock LLM + basic extraction)${NC}"
fi

echo -e "\n  ${DIM}Re-run this script anytime to update dependencies.${NC}\n"
