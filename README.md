# PainPoint: Lean Agent Orchestrator

**PainPoint** is a single-process, high-velocity orchestration engine built for 4GB RAM environments. It features the **"Glass Window" CLI**, a frictionless intake terminal that converts messy brain-dumps into strict, validated execution plans.

## 🚀 One-Step Installation

Get started immediately with a single command (Linux/macOS):

```bash
curl -sSL https://raw.githubusercontent.com/namanur/painpoint/master/setup.sh | bash
```

This script will:
1. Clone the repository (if not already present).
2. Create a virtual environment and install all dependencies.
3. Initialize a local SQLite database (`painpoint.db`).
4. Set up a global `painpoint` command in `~/.local/bin`.

## 🌍 Global Usage

Once installed, ensure `~/.local/bin` is in your `$PATH`. You can then run the intake terminal from **any directory**:

```bash
painpoint
```

## 🛠 Features

### 1. Interactive Intake (The Glass Window)
Run `painpoint` without arguments to open your preferred text editor. It automatically detects `nvim`, `vim`, `nano`, `mousepad`, or `gedit` based on your OS.

### 2. Agentic Prompting
Pass a direct prompt for non-interactive use (perfect for integration with Pi or Gemini):
```bash
painpoint "Plan a migration of my legacy CSV data to SQLite"
```

## 🏗 Architecture
* **Multi-DB Core:** Supports SQLite (default) and PostgreSQL.
* **Prompt Contracts:** Strict Pydantic validation for all agent instructions.
* **Tool Binding:** FastMCP for secure, extensible tool execution.
* **Headless Engine:** Single-process `asyncio` orchestration loop.

---
*Built for speed. Validated for integrity.*
