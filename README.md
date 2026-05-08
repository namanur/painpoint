# PainPoint: Lean Agent Orchestrator

**PainPoint** is a single-process, high-velocity orchestration engine built for 4GB RAM environments. It features the **"Glass Window" CLI**, a frictionless intake terminal that converts messy brain-dumps into strict, validated execution plans.

## 🚀 One-Command Setup

Get started immediately with the automated setup script (Linux/macOS):

```bash
bash setup.sh
```

This will create a virtual environment, install dependencies, and initialize your local SQLite database (`painpoint.db`).

## 🌍 Global Installation

To use `painpoint` from any directory on your system:

1. Run the setup script above.
2. Add the following to your `.bashrc` or `.zshrc`:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```
3. You can now trigger the intake terminal from anywhere:
   ```bash
   painpoint
   ```

## 🛠 Usage

### 1. Interactive Intake (The Glass Window)
Run `painpoint` without arguments to open your preferred text editor.
* **Linux/Unix:** Automatically detects `nvim`, `vim`, `nano`, `mousepad`, or `gedit`.
* **macOS:** Tries terminal editors first, falls back to TextEdit (`open -t`).
* **Windows:** Falls back to `notepad`.
* **Custom:** Set the `EDITOR` environment variable (e.g., `export EDITOR="code --wait"`).

### 2. Agentic Prompting
Pass a direct prompt for non-interactive use (perfect for integration with Pi or Gemini):
```bash
painpoint "Plan a migration of my legacy CSV data to SQLite"
```

## 🏗 Architecture
* **Multi-DB Core:** Supports SQLite (default for dev) and PostgreSQL (for VPS).
* **Prompt Contracts:** Strict Pydantic validation for all agent instructions.
* **Tool Binding:** FastMCP for secure, extensible tool execution.
* **Headless Engine:** Single-process `asyncio` orchestration loop.

---
*Built for speed. Validated for integrity.*
