"""DAG executor engine.

Reads the task board, resolves dependencies via topological sort,
and dispatches agent tasks with maximum parallelism.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import OrchestratorConfig
from .taskboard import Task, TaskBoard, TaskStatus
from .state import StateManager
from .runner import AgentRunner, TaskResult
from .reporter import OrchestratorReporter
from .prompts.base import build_system_prompt


@dataclass
class PhaseResult:
    """Result of executing an entire phase."""

    phase: int
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    total_seconds: float = 0
    total_cost_cents: float = 0


class DAGExecutor:
    """Executes tasks respecting dependencies, with max parallelism."""

    def __init__(
        self,
        config: OrchestratorConfig,
        taskboard: TaskBoard,
        state: StateManager,
        runner: AgentRunner,
        reporter: OrchestratorReporter,
    ) -> None:
        self.config = config
        self.taskboard = taskboard
        self.state = state
        self.runner = runner
        self.reporter = reporter

    def get_dag_levels(self, phase: int) -> list[list[str]]:
        """Compute DAG levels for a phase.

        Returns a list of lists, where each inner list contains task IDs
        that can run in parallel (all their dependencies are in prior levels).
        """
        tasks = self.taskboard.get_tasks_for_phase(phase)
        if not tasks:
            return []

        task_map = {t.id: t for t in tasks}
        completed_ids: set[str] = set()
        levels: list[list[str]] = []

        remaining = set(task_map.keys())

        while remaining:
            # Find tasks whose dependencies are all completed
            ready = []
            for tid in remaining:
                task = task_map[tid]
                # Dependencies can be from any phase (prior phases assumed done)
                deps_in_phase = [d for d in task.dependencies if d in task_map]
                if all(d in completed_ids for d in deps_in_phase):
                    ready.append(tid)

            if not ready:
                # Circular dependency or unresolvable
                levels.append(list(remaining))
                break

            levels.append(sorted(ready))
            for tid in ready:
                completed_ids.add(tid)
                remaining.discard(tid)

        return levels

    def dry_run(self, phase: int) -> None:
        """Show execution plan without running anything."""
        tasks = self.taskboard.get_tasks_for_phase(phase)
        levels = self.get_dag_levels(phase)
        self.reporter.dry_run_plan(tasks, levels)

    def execute_phase(self, phase: int) -> PhaseResult:
        """Execute all tasks in a phase, respecting dependencies.

        Uses a thread pool to run agents in parallel.
        """
        tasks = self.taskboard.get_tasks_for_phase(phase)
        if not tasks:
            self.reporter.phase_complete(phase, 0, 0, 0, 0)
            return PhaseResult(phase=phase)

        self.reporter.phase_start(phase, len(tasks))
        phase_run_id = self.state.start_phase(phase, len(tasks))
        start_time = time.time()

        result = PhaseResult(phase=phase)
        task_map = {t.id: t for t in tasks}

        # Track completion status
        completed_ids: set[str] = set()
        failed_ids: set[str] = set()
        running_futures: dict[str, Future[TaskResult]] = {}

        with ThreadPoolExecutor(max_workers=self.config.max_parallel) as pool:
            while True:
                # Check if all tasks are done
                all_done = all(
                    t.id in completed_ids or t.id in failed_ids
                    or t.status in (TaskStatus.BLOCKED, TaskStatus.SKIPPED)
                    for t in tasks
                )
                if all_done and not running_futures:
                    break

                # Find ready tasks
                ready = []
                for task in tasks:
                    if task.id in completed_ids or task.id in failed_ids:
                        continue
                    if task.id in running_futures:
                        continue
                    if task.status in (TaskStatus.BLOCKED, TaskStatus.SKIPPED):
                        continue

                    # Check dependencies
                    deps_met = all(
                        d in completed_ids
                        for d in task.dependencies
                        if d in task_map
                    )
                    deps_failed = any(
                        d in failed_ids
                        for d in task.dependencies
                        if d in task_map
                    )

                    if deps_failed:
                        # Block this task
                        failed_dep = next(
                            d for d in task.dependencies if d in failed_ids
                        )
                        self.taskboard.update_status(
                            task.id, TaskStatus.BLOCKED
                        )
                        self.reporter.task_blocked(task.id, failed_dep)
                        result.blocked.append(task.id)
                        continue

                    if deps_met:
                        ready.append(task)

                # Launch ready tasks (up to max_parallel)
                available_slots = self.config.max_parallel - len(running_futures)
                for task in ready[:available_slots]:
                    self.taskboard.update_status(task.id, TaskStatus.RUNNING)
                    self.reporter.task_start(task.id, task.agent)

                    future = pool.submit(
                        self._run_single_task, task
                    )
                    running_futures[task.id] = future

                # Wait for any running task to complete
                if running_futures:
                    # Poll futures (check every 2 seconds)
                    done_ids = []
                    for tid, future in running_futures.items():
                        if future.done():
                            done_ids.append(tid)

                    if not done_ids:
                        time.sleep(2)
                        continue

                    for tid in done_ids:
                        future = running_futures.pop(tid)
                        task_result = future.result()

                        if task_result.success:
                            completed_ids.add(tid)
                            result.completed.append(tid)
                            result.total_cost_cents += task_result.cost_cents
                            self.taskboard.update_status(
                                tid, TaskStatus.COMPLETED
                            )
                            self.reporter.task_complete(
                                tid, task_result.duration_seconds
                            )
                        else:
                            failed_ids.add(tid)
                            result.failed.append(tid)
                            self.taskboard.update_status(
                                tid, TaskStatus.FAILED,
                                error=task_result.error,
                            )
                            self.reporter.task_failed(
                                tid, task_result.error or "Unknown error"
                            )

        # Phase complete
        result.total_seconds = time.time() - start_time
        self.state.complete_phase(
            phase_run_id,
            completed=len(result.completed),
            failed=len(result.failed),
            total_cost=result.total_cost_cents,
        )
        self.reporter.phase_complete(
            phase,
            len(result.completed),
            len(result.failed),
            result.total_seconds,
            result.total_cost_cents,
        )
        return result

    def _run_single_task(self, task: Task) -> TaskResult:
        """Run a single task via the agent runner."""
        model = self.config.get_model_for_agent(task.agent)
        system_prompt = build_system_prompt(
            agent_type=task.agent,
            project_root=self.config.project_root,
            skills_dir=self.config.skills_dir,
        )

        return self.runner.run_task(
            task_id=task.id,
            system_prompt=system_prompt,
            task_prompt=self._build_task_prompt(task),
            model=model,
            timeout=task.timeout or self.config.default_timeout,
            phase=task.phase,
            agent_type=task.agent,
        )

    def _build_task_prompt(self, task: Task) -> str:
        """Build the user-facing task prompt for an agent."""
        parts = [
            f"# Task: {task.id}",
            "",
            task.description.strip(),
            "",
        ]

        if task.files:
            parts.append("## Files to create/modify:")
            for f in task.files:
                parts.append(f"- {f}")
            parts.append("")

        if task.acceptance:
            parts.append("## Acceptance criteria:")
            for a in task.acceptance:
                parts.append(f"- {a}")
            parts.append("")

        parts.extend([
            "## Instructions:",
            "1. Read any existing files you need to understand before writing.",
            "2. Create or modify the files listed above.",
            "3. Ensure all acceptance criteria are met.",
            "4. Run linting and type checking on your code.",
            "5. When finished, provide a summary of what you built.",
        ])

        return "\n".join(parts)
