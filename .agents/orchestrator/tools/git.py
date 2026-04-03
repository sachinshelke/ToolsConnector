"""Git tools for agent sessions.

Provides common git operations as tool definitions that agents can invoke
through the Anthropic API tool_use interface. Each tool maps to a single
git sub-command executed via subprocess.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

GIT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "git_status",
        "description": (
            "Show the working-tree status. Returns staged, unstaged, and "
            "untracked file information. Use before committing to review "
            "what has changed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "git_diff",
        "description": (
            "Show unstaged changes in the working tree. Optionally "
            "narrow the diff to a specific file or directory path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Optional file or directory path to restrict the diff to."
                    ),
                },
            },
        },
    },
    {
        "name": "git_add",
        "description": (
            "Stage file(s) for the next commit. Pass '.' to stage all "
            "changes or a specific relative path for targeted staging."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Relative file or directory path to stage. "
                        "Use '.' to stage everything."
                    ),
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "git_commit",
        "description": (
            "Create a new commit with the staged changes. Provide a concise, "
            "descriptive commit message explaining what changed and why."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The commit message.",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "git_branch",
        "description": (
            "Create a new git branch. Optionally check it out immediately. "
            "The branch is created from the current HEAD."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the new branch.",
                },
                "checkout": {
                    "type": "boolean",
                    "description": (
                        "If true, create and switch to the branch in one step "
                        "(git checkout -b). Defaults to false."
                    ),
                    "default": False,
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "git_log",
        "description": (
            "Show recent commit history as a compact one-line-per-commit log."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": (
                        "Number of commits to show. Defaults to 10."
                    ),
                    "default": 10,
                },
            },
        },
    },
]


def _run_git(
    cmd: list[str],
    project_root: Path,
) -> str:
    """Run a git command and return combined stdout/stderr.

    Args:
        cmd: The git command as a list of arguments (e.g.
            ``["git", "status"]``).
        project_root: Working directory for the subprocess.

    Returns:
        The command output, or a human-readable error message.
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return f"Error: git command timed out: {' '.join(cmd)}"
    except Exception as exc:
        return f"Error running git: {exc}"

    output_parts: list[str] = []
    if result.stdout:
        output_parts.append(result.stdout)
    if result.stderr:
        output_parts.append(result.stderr)

    output = "\n".join(output_parts).strip() if output_parts else "(no output)"

    if result.returncode != 0:
        output = f"[exit code {result.returncode}]\n{output}"

    return output


def execute_git_tool(
    name: str,
    args: dict[str, Any],
    project_root: Path,
) -> str:
    """Execute a git tool and return the result.

    Args:
        name: One of the tool names defined in ``GIT_TOOLS``.
        args: Tool arguments parsed from the LLM response.
        project_root: Absolute path to the repository root, used as the
            working directory for every git invocation.

    Returns:
        The git command output, or a human-readable error string.
    """
    if name == "git_status":
        return _run_git(["git", "status"], project_root)

    elif name == "git_diff":
        cmd = ["git", "diff"]
        path = args.get("path")
        if path:
            cmd += ["--", path]
        return _run_git(cmd, project_root)

    elif name == "git_add":
        path = args.get("path")
        if not path:
            return "Error: 'path' argument is required for git_add."
        return _run_git(["git", "add", path], project_root)

    elif name == "git_commit":
        message = args.get("message")
        if not message:
            return "Error: 'message' argument is required for git_commit."
        return _run_git(["git", "commit", "-m", message], project_root)

    elif name == "git_branch":
        branch_name = args.get("name")
        if not branch_name:
            return "Error: 'name' argument is required for git_branch."
        checkout: bool = args.get("checkout", False)
        if checkout:
            return _run_git(
                ["git", "checkout", "-b", branch_name], project_root
            )
        return _run_git(["git", "branch", branch_name], project_root)

    elif name == "git_log":
        count = args.get("count", 10)
        return _run_git(
            ["git", "log", "--oneline", "-n", str(count)], project_root
        )

    return f"Error: Unknown git tool '{name}'."
