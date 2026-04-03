"""Task board parser and manager.

Reads/writes .agents/taskboard.yaml — the source of truth for all work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class TaskStatus(str, Enum):
    """Status of a task in the task board."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class Task:
    """A single task in the task board."""

    id: str
    agent: str
    phase: int
    priority: int
    status: TaskStatus
    description: str
    files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    timeout: int | None = None
    error: str | None = None
    branch: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Create a Task from a YAML dict."""
        return cls(
            id=data["id"],
            agent=data["agent"],
            phase=data.get("phase", 0),
            priority=data.get("priority", 99),
            status=TaskStatus(data.get("status", "pending")),
            description=data.get("description", ""),
            files=data.get("files", []),
            dependencies=data.get("dependencies", []),
            acceptance=data.get("acceptance", []),
            timeout=data.get("timeout"),
            error=data.get("error"),
            branch=data.get("branch"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize task to a dict for YAML output."""
        d: dict[str, Any] = {
            "id": self.id,
            "agent": self.agent,
            "phase": self.phase,
            "priority": self.priority,
            "status": self.status.value,
            "description": self.description,
        }
        if self.files:
            d["files"] = self.files
        if self.dependencies:
            d["dependencies"] = self.dependencies
        if self.acceptance:
            d["acceptance"] = self.acceptance
        if self.timeout:
            d["timeout"] = self.timeout
        if self.error:
            d["error"] = self.error
        if self.branch:
            d["branch"] = self.branch
        return d


class TaskBoard:
    """Manages the task board YAML file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {}
        self._tasks: list[Task] = []
        self._load()

    def _load(self) -> None:
        """Load task board from YAML."""
        if not self.path.exists():
            self._data = {"version": "1.0", "project": "toolsconnector", "tasks": []}
            self._tasks = []
            return

        with open(self.path) as f:
            self._data = yaml.safe_load(f) or {}

        self._tasks = [
            Task.from_dict(t) for t in self._data.get("tasks", [])
        ]

    def save(self) -> None:
        """Write task board back to YAML."""
        self._data["tasks"] = [t.to_dict() for t in self._tasks]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            yaml.dump(
                self._data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=120,
            )

    @property
    def project(self) -> str:
        return self._data.get("project", "toolsconnector")

    @property
    def current_phase(self) -> int:
        return self._data.get("current_phase", 0)

    @property
    def tasks(self) -> list[Task]:
        return self._tasks

    def get_tasks_for_phase(self, phase: int) -> list[Task]:
        """Get all tasks for a given phase, sorted by priority."""
        return sorted(
            [t for t in self._tasks if t.phase == phase],
            key=lambda t: t.priority,
        )

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        for t in self._tasks:
            if t.id == task_id:
                return t
        return None

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: str | None = None,
        branch: str | None = None,
    ) -> None:
        """Update a task's status and persist."""
        task = self.get_task(task_id)
        if task:
            task.status = status
            if error is not None:
                task.error = error
            if branch is not None:
                task.branch = branch
            self.save()

    def get_ready_tasks(self, phase: int) -> list[Task]:
        """Get tasks whose dependencies are all completed."""
        completed_ids = {
            t.id for t in self._tasks if t.status == TaskStatus.COMPLETED
        }
        phase_tasks = self.get_tasks_for_phase(phase)
        ready = []
        for task in phase_tasks:
            if task.status != TaskStatus.PENDING:
                continue
            deps_met = all(dep in completed_ids for dep in task.dependencies)
            if deps_met:
                ready.append(task)
        return ready

    def get_blocked_by(self, task_id: str) -> list[Task]:
        """Get tasks that depend on the given task."""
        return [
            t for t in self._tasks
            if task_id in t.dependencies
        ]

    def is_phase_complete(self, phase: int) -> bool:
        """Check if all tasks in a phase are completed."""
        phase_tasks = self.get_tasks_for_phase(phase)
        return all(t.status == TaskStatus.COMPLETED for t in phase_tasks)

    def get_phase_summary(self, phase: int) -> dict[str, int]:
        """Get count of tasks per status for a phase."""
        phase_tasks = self.get_tasks_for_phase(phase)
        summary: dict[str, int] = {}
        for task in phase_tasks:
            key = task.status.value
            summary[key] = summary.get(key, 0) + 1
        return summary
