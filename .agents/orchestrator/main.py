"""Orchestrator CLI entry point.

Usage:
    python -m agents.orchestrator run --phase 0
    python -m agents.orchestrator run --phase 0 --dry-run
    python -m agents.orchestrator status
    python -m agents.orchestrator status --phase 0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Imports here are typing-only — actual modules are imported lazily inside
# command handlers below to keep CLI startup snappy and avoid import-time
# side effects from the full orchestrator stack.
if TYPE_CHECKING:
    from .config import OrchestratorConfig
    from .reporter import OrchestratorReporter
    from .taskboard import TaskBoard


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the orchestrator CLI."""
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="ToolsConnector Agent Army Orchestrator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # --- run command ---
    run_parser = subparsers.add_parser("run", help="Execute a phase")
    run_parser.add_argument(
        "--phase", type=int, required=True,
        help="Phase number to execute",
    )
    run_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show execution plan without running",
    )
    run_parser.add_argument(
        "--task", type=str, default=None,
        help="Run a single task by ID (useful for retrying)",
    )
    run_parser.add_argument(
        "--config", type=str, default=None,
        help="Path to orchestrator config YAML",
    )
    run_parser.add_argument(
        "--max-parallel", type=int, default=None,
        help="Override max parallel agents",
    )

    # --- status command ---
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.add_argument(
        "--phase", type=int, default=None,
        help="Show status for a specific phase",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    # Resolve project root (find pyproject.toml)
    project_root = _find_project_root()
    if not project_root:
        print("Error: Could not find project root (no pyproject.toml found).")
        return 1

    if args.command == "run":
        return _cmd_run(args, project_root)
    elif args.command == "status":
        return _cmd_status(args, project_root)

    return 1


def _cmd_run(args: argparse.Namespace, project_root: Path) -> int:
    """Execute the 'run' command."""
    from .config import OrchestratorConfig
    from .engine import DAGExecutor
    from .reporter import OrchestratorReporter
    from .runner import AgentRunner
    from .state import StateManager
    from .taskboard import TaskBoard

    # Load config
    config_path = Path(args.config) if args.config else None
    config = OrchestratorConfig.load(config_path)
    config.project_root = project_root

    if args.max_parallel:
        config.max_parallel = args.max_parallel

    # Check API key
    if not config.api_key and not args.dry_run:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        print("Set it with: export ANTHROPIC_API_KEY=your-key-here")
        return 1

    # Load task board
    taskboard_path = project_root / config.taskboard_path
    if not taskboard_path.exists():
        print(f"Error: Task board not found at {taskboard_path}")
        return 1

    taskboard = TaskBoard(taskboard_path)
    reporter = OrchestratorReporter()

    # Dry run — just show the plan
    if args.dry_run:
        state = StateManager(project_root / config.state_db_path)
        runner = AgentRunner(
            api_key=config.api_key,
            project_root=project_root,
            state=state,
            allowed_dirs=config.sandbox.allowed_dirs,
            blocked_commands=config.sandbox.blocked_commands,
        )
        executor = DAGExecutor(config, taskboard, state, runner, reporter)
        executor.dry_run(args.phase)
        state.close()
        return 0

    # Single task mode
    if args.task:
        return _run_single_task(args, config, taskboard, project_root, reporter)

    # Full phase execution
    state = StateManager(project_root / config.state_db_path)
    runner = AgentRunner(
        api_key=config.api_key,
        project_root=project_root,
        state=state,
        allowed_dirs=config.sandbox.allowed_dirs,
        blocked_commands=config.sandbox.blocked_commands,
    )
    executor = DAGExecutor(config, taskboard, state, runner, reporter)

    print(f"\nStarting Phase {args.phase} execution...")
    print(f"Model: {config.default_model}")
    print(f"Max parallel: {config.max_parallel}")
    print()

    result = executor.execute_phase(args.phase)
    state.close()

    if result.failed:
        print(f"\nPhase {args.phase} completed with {len(result.failed)} failures.")
        return 1

    return 0


def _run_single_task(
    args: argparse.Namespace,
    config: OrchestratorConfig,
    taskboard: TaskBoard,
    project_root: Path,
    reporter: OrchestratorReporter,
) -> int:
    """Run a single task by ID."""
    from .prompts.base import build_system_prompt
    from .runner import AgentRunner
    from .state import StateManager

    task = taskboard.get_task(args.task)
    if not task:
        print(f"Error: Task '{args.task}' not found in task board.")
        return 1

    state = StateManager(project_root / config.state_db_path)
    runner = AgentRunner(
        api_key=config.api_key,
        project_root=project_root,
        state=state,
        allowed_dirs=config.sandbox.allowed_dirs,
        blocked_commands=config.sandbox.blocked_commands,
    )

    model = config.get_model_for_agent(task.agent)
    reporter.task_start(task.id, task.agent)

    system_prompt = build_system_prompt(
        agent_type=task.agent,
        project_root=project_root,
        skills_dir=project_root / config.skills_dir,
    )

    # Build task prompt
    parts = [
        f"# Task: {task.id}\n",
        task.description.strip(),
    ]
    if task.files:
        parts.append("\n## Files to create/modify:")
        for f in task.files:
            parts.append(f"- {f}")
    if task.acceptance:
        parts.append("\n## Acceptance criteria:")
        for a in task.acceptance:
            parts.append(f"- {a}")
    parts.append(
        "\n## Instructions:\n"
        "1. Read existing files before modifying.\n"
        "2. Create/modify files listed above.\n"
        "3. Meet all acceptance criteria.\n"
        "4. Run linting and type checking.\n"
        "5. Summarize what you built."
    )

    result = runner.run_task(
        task_id=task.id,
        system_prompt=system_prompt,
        task_prompt="\n".join(parts),
        model=model,
        timeout=task.timeout or config.default_timeout,
        phase=task.phase,
        agent_type=task.agent,
    )

    if result.success:
        from .taskboard import TaskStatus
        taskboard.update_status(task.id, TaskStatus.COMPLETED)
        reporter.task_complete(task.id, result.duration_seconds)
    else:
        from .taskboard import TaskStatus
        taskboard.update_status(task.id, TaskStatus.FAILED, error=result.error)
        reporter.task_failed(task.id, result.error or "Unknown")

    state.close()
    return 0 if result.success else 1


def _cmd_status(args: argparse.Namespace, project_root: Path) -> int:
    """Show orchestrator status."""
    from .config import OrchestratorConfig
    from .taskboard import TaskBoard

    config = OrchestratorConfig.load()
    taskboard_path = project_root / config.taskboard_path

    if not taskboard_path.exists():
        print(f"No task board found at {taskboard_path}")
        return 1

    taskboard = TaskBoard(taskboard_path)

    if args.phase is not None:
        tasks = taskboard.get_tasks_for_phase(args.phase)
        print(f"\nPhase {args.phase}: {len(tasks)} tasks")
        print("-" * 60)
        for t in tasks:
            status_icon = {
                "pending": "○",
                "running": "▶",
                "completed": "✓",
                "failed": "✗",
                "blocked": "⊘",
                "skipped": "–",
            }.get(t.status.value, "?")
            print(f"  {status_icon} {t.id:<30} [{t.status.value}] → {t.agent}")
            if t.error:
                print(f"    Error: {t.error}")
    else:
        # Show all phases
        phases = set(t.phase for t in taskboard.tasks)
        for phase in sorted(phases):
            summary = taskboard.get_phase_summary(phase)
            total = sum(summary.values())
            print(f"\nPhase {phase}: {total} tasks — {summary}")

    return 0


def _find_project_root() -> Path | None:
    """Walk up from CWD to find pyproject.toml."""
    current = Path.cwd()
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Check root
    if (current / "pyproject.toml").exists():
        return current
    return None


if __name__ == "__main__":
    sys.exit(main())
