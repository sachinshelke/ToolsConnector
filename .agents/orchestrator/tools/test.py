"""Test tools for the agent army orchestrator.

Provides tool definitions and execution logic for running pytest, mypy, and ruff
against the ToolsConnector codebase.
"""

from __future__ import annotations

import subprocess
from typing import Any

TEST_TOOLS: list[dict[str, Any]] = [
    {
        "name": "run_tests",
        "description": "Run pytest on a given path (defaults to tests/).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File or directory to test. Defaults to 'tests/'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "run_typecheck",
        "description": "Run mypy --strict on a given path (defaults to toolsconnector/).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File or directory to typecheck. Defaults to 'toolsconnector/'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "run_lint",
        "description": "Run ruff check on a given path (defaults to toolsconnector/).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File or directory to lint. Defaults to 'toolsconnector/'.",
                },
            },
            "required": [],
        },
    },
]

_MAX_OUTPUT_CHARS = 10_000
_TIMEOUT_SECS = 300

_DEFAULT_PATHS: dict[str, str] = {
    "run_tests": "tests/",
    "run_typecheck": "toolsconnector/",
    "run_lint": "toolsconnector/",
}

_COMMANDS: dict[str, list[str]] = {
    "run_tests": ["python", "-m", "pytest", "{path}", "-v", "--tb=short"],
    "run_typecheck": ["python", "-m", "mypy", "{path}", "--strict"],
    "run_lint": ["python", "-m", "ruff", "check", "{path}"],
}


def execute_test_tool(
    name: str,
    args: dict[str, Any],
    project_root: str,
) -> str:
    """Execute a test tool by *name* with the given *args*.

    Parameters
    ----------
    name:
        One of ``run_tests``, ``run_typecheck``, or ``run_lint``.
    args:
        Tool arguments.  Accepts an optional ``path`` key.
    project_root:
        Absolute path to the repository root.  Commands are executed with
        ``cwd`` set to this directory.

    Returns
    -------
    str
        Combined stdout and stderr, capped at 10 000 characters.

    Raises
    ------
    ValueError
        If *name* is not a recognised test tool.
    """
    if name not in _COMMANDS:
        raise ValueError(
            f"Unknown test tool '{name}'. "
            f"Expected one of: {', '.join(_COMMANDS)}"
        )

    path = args.get("path", _DEFAULT_PATHS[name])
    cmd = [tok.replace("{path}", path) for tok in _COMMANDS[name]]

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECS,
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        output = f"Command timed out after {_TIMEOUT_SECS} seconds."
    except Exception as exc:  # noqa: BLE001
        output = f"Failed to execute command: {exc}"

    if len(output) > _MAX_OUTPUT_CHARS:
        output = output[:_MAX_OUTPUT_CHARS] + "\n... (output truncated)"

    return output
