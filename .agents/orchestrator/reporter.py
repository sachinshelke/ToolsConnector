"""Orchestrator reporter -- rich terminal output for agent army progress.

Falls back to plain ``print`` when the ``rich`` library is not installed.
"""

from __future__ import annotations

from typing import Any

try:
    from rich.console import Console
    from rich.table import Table

    _RICH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RICH_AVAILABLE = False


def _format_duration(total_secs: float) -> str:
    """Return a human-friendly ``Xm Ys`` duration string."""
    minutes = int(total_secs) // 60
    seconds = int(total_secs) % 60
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


class OrchestratorReporter:
    """Display orchestrator progress in the terminal.

    Uses ``rich`` for coloured, styled output when available.  If ``rich``
    is not installed the reporter falls back to plain ``print`` calls so
    that the orchestrator keeps working in minimal environments.
    """

    def __init__(self) -> None:
        if _RICH_AVAILABLE:
            self._console: Console | None = Console()
        else:
            self._console = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _print(self, message: str, style: str | None = None) -> None:
        """Print *message*, optionally with a Rich *style*."""
        if self._console is not None and style is not None:
            self._console.print(message, style=style)
        elif self._console is not None:
            self._console.print(message)
        else:
            print(message)

    # ------------------------------------------------------------------
    # Phase lifecycle
    # ------------------------------------------------------------------

    def phase_start(self, phase: int, total_tasks: int) -> None:
        """Print a prominent header at the start of a new execution phase."""
        header = f"=== Phase {phase} === ({total_tasks} tasks)"
        if self._console is not None:
            self._console.rule(f"[bold blue]Phase {phase}[/bold blue]  ({total_tasks} tasks)")
        else:
            print(f"\n{'=' * 60}")
            print(header)
            print("=" * 60)

    def phase_complete(
        self,
        phase: int,
        completed: int,
        failed: int,
        total_secs: float,
        cost_cents: float,
    ) -> None:
        """Print a summary line after a phase finishes."""
        duration = _format_duration(total_secs)
        summary = (
            f"Phase {phase} complete: "
            f"{completed} succeeded, {failed} failed "
            f"in {duration} (${cost_cents / 100:.2f})"
        )
        style = "bold green" if failed == 0 else "bold red"
        self._print(summary, style=style)

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------

    def task_start(self, task_id: str, agent: str) -> None:
        """Print a line when a task begins execution."""
        self._print(f"  \u25b6 {task_id} \u2192 {agent} (starting...)", style="yellow")

    def task_complete(self, task_id: str, duration_secs: float) -> None:
        """Print a line when a task finishes successfully."""
        duration = _format_duration(duration_secs)
        self._print(f"  \u2713 {task_id} \u2192 completed ({duration})", style="green")

    def task_failed(self, task_id: str, error: str) -> None:
        """Print a line when a task fails."""
        self._print(f"  \u2717 {task_id} \u2192 FAILED: {error}", style="red")

    def task_blocked(self, task_id: str, blocked_by: str) -> None:
        """Print a line when a task is blocked by another."""
        self._print(f"  \u2298 {task_id} \u2192 blocked by: {blocked_by}", style="dim")

    # ------------------------------------------------------------------
    # Dry-run / planning output
    # ------------------------------------------------------------------

    def dry_run_plan(
        self,
        tasks: list[dict[str, Any]],
        dag_order: list[list[str]],
    ) -> None:
        """Display the full execution plan without running anything.

        Parameters
        ----------
        tasks:
            List of task dicts.  Each dict should contain at least ``id``,
            ``agent``, and optionally ``depends_on``.
        dag_order:
            Topologically sorted groups of task IDs.  Each inner list
            represents a set of tasks that can run in parallel.
        """
        # Support both Task objects and dicts
        def _get(t: Any, key: str, default: Any = "") -> Any:
            if hasattr(t, key):
                return getattr(t, key)
            if isinstance(t, dict):
                return t.get(key, default)
            return default

        if self._console is not None:
            self._console.rule("[bold]Dry-Run Execution Plan[/bold]")

            table = Table(title="Tasks", show_lines=True)
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Agent", style="magenta")
            table.add_column("Depends On", style="dim")

            for task in tasks:
                dep_list = _get(task, "dependencies", [])
                deps = ", ".join(dep_list) if dep_list else "\u2014"
                table.add_row(
                    str(_get(task, "id")),
                    str(_get(task, "agent", "?")),
                    deps,
                )

            self._console.print(table)
            self._console.print()

            for level_idx, group in enumerate(dag_order):
                level_label = f"Level {level_idx} ({len(group)} parallel)"
                names = ", ".join(group)
                self._console.print(f"  [bold]{level_label}:[/bold] {names}")

            self._console.print()
        else:
            print("\n--- Dry-Run Execution Plan ---")
            print(f"{'ID':<30} {'Agent':<20} {'Depends On'}")
            print("-" * 70)
            for task in tasks:
                dep_list = _get(task, "dependencies", [])
                deps = ", ".join(dep_list) if dep_list else "\u2014"
                print(f"{str(_get(task, 'id')):<30} {str(_get(task, 'agent', '?')):<20} {deps}")
            print()
            for level_idx, group in enumerate(dag_order):
                print(f"  Level {level_idx} ({len(group)} parallel): {', '.join(group)}")
            print()
