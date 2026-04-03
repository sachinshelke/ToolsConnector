"""Persistent state manager using SQLite.

Tracks agent sessions, task progress, and execution logs across runs.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateManager:
    """SQLite-backed state persistence for the orchestrator."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS task_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                phase INTEGER NOT NULL,
                agent_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_seconds REAL,
                model TEXT,
                branch TEXT,
                error TEXT,
                token_usage_input INTEGER DEFAULT 0,
                token_usage_output INTEGER DEFAULT 0,
                cost_cents REAL DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS phase_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                failed_tasks INTEGER DEFAULT 0,
                total_cost_cents REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_run_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_name TEXT,
                tool_input TEXT,
                tool_output TEXT,
                FOREIGN KEY (task_run_id) REFERENCES task_runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_task_runs_task_id
                ON task_runs(task_id);
            CREATE INDEX IF NOT EXISTS idx_task_runs_phase
                ON task_runs(phase);
            CREATE INDEX IF NOT EXISTS idx_agent_logs_task_run
                ON agent_logs(task_run_id);
        """)
        self._conn.commit()

    def start_phase(self, phase: int, total_tasks: int) -> int:
        """Record the start of a phase execution. Returns phase_run id."""
        cursor = self._conn.execute(
            """INSERT INTO phase_runs (phase, status, started_at, total_tasks)
               VALUES (?, 'running', ?, ?)""",
            (phase, _now(), total_tasks),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def complete_phase(
        self,
        phase_run_id: int,
        completed: int,
        failed: int,
        total_cost: float,
    ) -> None:
        """Record phase completion."""
        status = "completed" if failed == 0 else "partial"
        self._conn.execute(
            """UPDATE phase_runs
               SET status=?, completed_at=?, completed_tasks=?,
                   failed_tasks=?, total_cost_cents=?
               WHERE id=?""",
            (status, _now(), completed, failed, total_cost, phase_run_id),
        )
        self._conn.commit()

    def start_task_run(
        self,
        task_id: str,
        phase: int,
        agent_type: str,
        model: str,
        branch: str | None = None,
    ) -> int:
        """Record the start of a task run. Returns task_run id."""
        cursor = self._conn.execute(
            """INSERT INTO task_runs
               (task_id, phase, agent_type, status, started_at, model, branch)
               VALUES (?, ?, ?, 'running', ?, ?, ?)""",
            (task_id, phase, agent_type, _now(), model, branch),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def complete_task_run(
        self,
        task_run_id: int,
        status: str,
        error: str | None = None,
        token_input: int = 0,
        token_output: int = 0,
        cost_cents: float = 0,
    ) -> None:
        """Record task completion."""
        started = self._conn.execute(
            "SELECT started_at FROM task_runs WHERE id=?", (task_run_id,)
        ).fetchone()
        duration = 0.0
        if started:
            start_dt = datetime.fromisoformat(started["started_at"])
            duration = (datetime.now(timezone.utc) - start_dt).total_seconds()

        self._conn.execute(
            """UPDATE task_runs
               SET status=?, completed_at=?, duration_seconds=?,
                   error=?, token_usage_input=?, token_usage_output=?,
                   cost_cents=?
               WHERE id=?""",
            (
                status, _now(), duration, error,
                token_input, token_output, cost_cents, task_run_id,
            ),
        )
        self._conn.commit()

    def log_agent_message(
        self,
        task_run_id: int,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_input: str | None = None,
        tool_output: str | None = None,
    ) -> None:
        """Log an agent conversation message."""
        self._conn.execute(
            """INSERT INTO agent_logs
               (task_run_id, timestamp, role, content,
                tool_name, tool_input, tool_output)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task_run_id, _now(), role, content,
             tool_name, tool_input, tool_output),
        )
        self._conn.commit()

    def get_task_history(self, task_id: str) -> list[dict[str, Any]]:
        """Get all runs for a task."""
        rows = self._conn.execute(
            "SELECT * FROM task_runs WHERE task_id=? ORDER BY started_at DESC",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_phase_history(self, phase: int) -> list[dict[str, Any]]:
        """Get all runs for a phase."""
        rows = self._conn.execute(
            "SELECT * FROM phase_runs WHERE phase=? ORDER BY started_at DESC",
            (phase,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_total_cost(self) -> float:
        """Get total cost across all runs in cents."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(cost_cents), 0) as total FROM task_runs"
        ).fetchone()
        return float(row["total"]) if row else 0.0

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


def _now() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()
