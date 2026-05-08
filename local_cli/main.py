"""
Project Genesis: Intake Terminal
=================================
Glass Window CLI - Opens native editor for frictionless brain dumps.

The user dumps their messy ideas, saves, and closes. The CLI
immediately ingests the file and streams compilation status.

Signal Handling: Graceful shutdown on SIGINT/SIGTERM.
"""

import asyncio
import os
import re
import signal
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# Import from src for LLM compilation
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from compiler.extraction import compile_workflow
from models.prompt_contract import PromptContract

console = Console()

# Shutdown flag for graceful exit
_shutdown_requested = False


def _handle_shutdown(signum, frame):
    """Graceful shutdown handler for SIGINT/SIGTERM."""
    global _shutdown_requested
    if _shutdown_requested:
        console.print("\n[bold red]Force exit requested. Goodbye![/bold red]")
        sys.exit(1)

    _shutdown_requested = True
    console.print(
        "\n[bold yellow]Shutdown requested... completing current step.[/bold yellow]"
    )


# Register signal handlers
signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)


def _basic_extraction(text: str) -> list:
    """
    Simple fallback extraction when LLM is unavailable.
    Parses text into basic nodes based on common patterns.
    """
    # Split by common delimiters: numbered lists, newlines, "then", "next", etc.
    sentences = re.split(r"\n+|(?=\d+\.)|(?<!\w)\.\s+(?=\w)|(?<=\w)\s+(?=[A-Z])", text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s) > 10]

    nodes = []
    for i, sentence in enumerate(sentences[:10]):  # Limit to 10 nodes
        nodes.append(
            {
                "id": f"node_{i + 1}",
                "role": f"Execute: {sentence[:100]}",
                "constraints": ["Follow plan exactly"],
                "allowed_tools": ["shell", "file_write"],
                "forbidden_actions": [],
                "decision_rules": {"success": "next", "failure": "retry"},
                "max_retries": 3,
            }
        )

    return nodes


async def compile_messy_dump(raw_text: str) -> str:
    """
    Compile messy brain dump into structured plan.

    Uses the LLM compiler from extraction.py with fallback to
    basic text parsing when LLM is unavailable.
    """
    global _shutdown_requested

    if _shutdown_requested:
        return "# Compilation Cancelled\n\nShutdown was requested."

    contracts = []

    # Phase 1: LLM Compilation
    with console.status("[cyan]Compiler Agent analyzing workflow...", spinner="dots"):
        try:
            # compile_workflow returns a list of dictionaries that have been Pydantic-validated
            raw_nodes = await compile_workflow(raw_text)

            # Convert dicts back to PromptContract objects for the UI/Markdown builder
            contracts = [PromptContract(**node) for node in raw_nodes]
            console.print(
                f"[green]✔ Compiled {len(contracts)} validated contracts.[/green]"
            )
        except Exception as e:
            console.print(f"[yellow]⚠ LLM compilation failed: {e}[/yellow]")
            console.print("[dim]Falling back to basic extraction...[/dim]")
            # Fallback: simple extraction from text
            fallback_nodes = _basic_extraction(raw_text)
            contracts = [PromptContract(**node) for node in fallback_nodes]

    if _shutdown_requested:
        return "# Compilation Cancelled\n\nShutdown was requested."

    # Phase 2: Generate Plan Markdown
    with console.status("[cyan]Generating Plan Document...", spinner="dots"):
        await asyncio.sleep(0.1)

    plan = _build_plan_markdown(contracts)
    console.print("[green]✔ Plan Generated.[/green]")

    return plan


def _build_plan_markdown(contracts: list) -> str:
    """Build the structured plan markdown from validated contracts."""
    lines = [
        "# Project Genesis Plan",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Graph Structure",
        "",
    ]

    # Nodes
    if contracts:
        lines.append("### Nodes")
        lines.append("")
        for i, contract in enumerate(contracts):
            node_id = f"node_{i + 1}"
            desc = contract.role
            # Truncate long descriptions
            if len(desc) > 150:
                desc = desc[:147] + "..."
            lines.append(f"- **{node_id}**: {desc}")
        lines.append("")

    # Extract edges from decision_rules
    edges = []
    for i, contract in enumerate(contracts):
        rules = contract.decision_rules
        if rules:
            for condition, target in rules.items():
                node_id = f"node_{i + 1}"
                edges.append(
                    {
                        "source": node_id,
                        "target": target,
                        "condition": condition,
                    }
                )
        elif i + 1 < len(contracts):
            # Implicit linear flow if no rules defined
            edges.append(
                {
                    "source": f"node_{i + 1}",
                    "target": f"node_{i + 2}",
                    "condition": "success",
                }
            )

    if edges:
        lines.append("### Edges")
        lines.append("")
        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            cond = edge.get("condition", "")
            cond_str = f" (if: {cond})" if cond else ""
            lines.append(f"- `{src}` → `{tgt}`{cond_str}")
        lines.append("")

    # Contracts
    if contracts:
        lines.append("## Prompt Contracts")
        lines.append("")
        for i, contract in enumerate(contracts, 1):
            lines.append(f"### Contract {i}")
            lines.append(f"- **Role:** {contract.role}")
            lines.append(f"- **Max Retries:** {contract.max_retries}")
            lines.append(
                f"- **Allowed Tools:** {', '.join(contract.allowed_tools) or 'none'}"
            )
            lines.append(
                f"- **Forbidden Actions:** {', '.join(contract.forbidden_actions) or 'none'}"
            )

            if contract.constraints:
                lines.append("- **Constraints:**")
                for c in contract.constraints:
                    lines.append(f"  - {c}")

            lines.append("")

    lines.append("---")
    lines.append("*Generated by Project Genesis Glass Window CLI*")

    return "\n".join(lines)


def _open_editor_for_input(prompt: str = "Enter your ideas below:") -> str | None:
    """
    Open the best available text editor for frictionless input.
    Detects OS and common editors (nvim, nano, notepad, etc.).

    Returns:
        The edited content, or None if cancelled/empty.
    """
    # Priority 1: User defined $EDITOR
    editor = os.environ.get("EDITOR")

    # Priority 2: OS-specific defaults
    if not editor:
        if sys.platform == "win32":
            # Windows: notepad is guaranteed
            editor = "notepad"
        elif sys.platform == "darwin":
            # macOS: 'open -t' opens default text editor (usually TextEdit)
            # but we prefer terminal editors if available
            for e in ["nvim", "vim", "nano"]:
                if (
                    subprocess.call(
                        ["which", e],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    == 0
                ):
                    editor = e
                    break
            if not editor:
                editor = "open -t"
        else:
            # Linux/Unix: Try common ones in order of "power"
            for e in ["nvim", "vim", "nano", "mousepad", "gedit"]:
                if (
                    subprocess.call(
                        ["which", e],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    == 0
                ):
                    editor = e
                    break
            if not editor:
                editor = "vi"  # POSIX standard fallback

    # Create marker comment for user guidance
    marker = "\n\n# --- DUMP YOUR MESSY IDEAS ABOVE THIS LINE ---\n"
    initial_content = f"{prompt}\n\n{marker}"

    # Create temp file
    fd, filepath = tempfile.mkstemp(suffix=".md", prefix="genesis_")

    try:
        with os.fdopen(fd, "w") as f:
            f.write(initial_content)

        # Handle editors that need 'open' or specific flags
        if "open -t" in editor:
            subprocess.call(["open", "-t", "-W", filepath])
        else:
            # For terminal editors, use shell=True if the string contains args
            subprocess.call(f"{editor} {filepath}", shell=True)

        # Read the result
        with open(filepath, "r") as f:
            content = f.read()

        # Extract only the content before the marker
        clean_content = content.split(marker)[0].strip()

        return clean_content if clean_content else None

    finally:
        # Clean up temp file
        try:
            os.unlink(filepath)
        except OSError:
            pass


@click.command()
@click.argument("prompt", required=False)
@click.option("--session-dir", default="sessions", help="Directory for plan output")
@click.option("--quiet", "-q", is_flag=True, help="Suppress verbose output")
def intake(prompt: str | None, session_dir: str, quiet: bool):
    """
    Open the Glass Window intake terminal.

    Accepts an optional PROMPT argument for direct compilation.
    If no prompt is provided, opens a native text editor for brain dumping.
    """
    console.print(
        Panel(
            "[bold cyan]Project Genesis: Glass Window Intake[/bold cyan]\n"
            "[dim]Dump your messy ideas. Save. Close. Plan.[/dim]",
            expand=False,
        )
    )

    # Check for graceful shutdown
    if _shutdown_requested:
        console.print("[bold red]Shutdown in progress. Try again later.[/bold red]")
        return

    raw_dump = None
    if prompt:
        raw_dump = prompt
        console.print(
            f"\n[bold green]Using provided prompt:[/bold green] [dim]{prompt}[/dim]"
        )
    else:
        console.print("\n[bold]Opening editor for brain-dump...[/bold]")
        console.print(
            f"[dim]Using: {os.environ.get('EDITOR', 'nano')} "
            f"(set $EDITOR to customize)[/dim]"
        )
        # Open editor for input
        raw_dump = _open_editor_for_input("Describe your task or goal:")

    if raw_dump is None or not raw_dump.strip():
        console.print("[bold red]Intake cancelled. No data provided.[/bold red]")
        return

    if not quiet:
        console.print(
            f"\n[bold yellow]Ingesting {len(raw_dump)} characters...[/bold yellow]"
        )
        console.print("[dim]Preview:[/dim]")
        preview = raw_dump[:200] + "..." if len(raw_dump) > 200 else raw_dump
        console.print(Panel(preview, title="[dim]Your Dump[/dim]", expand=False))

    # Run async compilation
    plan_markdown = asyncio.run(compile_messy_dump(raw_dump))

    if _shutdown_requested:
        console.print(
            "[bold yellow]Compilation cancelled due to shutdown request.[/bold yellow]"
        )
        return

    # Ensure session directory exists
    session_path = Path(session_dir)
    session_path.mkdir(parents=True, exist_ok=True)

    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = session_path / f"plan_{timestamp}.md"

    # Write plan to file
    with open(filename, "w") as f:
        f.write(plan_markdown)

    console.print(f"\n[bold green]✓ Planning Complete![/bold green]")
    console.print(f"[dim]Saved to: {filename}[/dim]")

    if not quiet:
        console.print("\n")
        console.print(Markdown(plan_markdown))


if __name__ == "__main__":
    intake()
