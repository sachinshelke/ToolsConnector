"""Shell tools for agent sessions.

Provides a sandboxed shell execution tool that agents can use to run
commands within the project directory. Commands are validated against
a configurable blocklist before execution.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

_OUTPUT_CAP = 10_000

SHELL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "run_command",
        "description": (
            "Run a shell command in the project directory and return its "
            "output. Use for build steps, linting, test execution, or any "
            "CLI task that doesn't have a dedicated tool. The command runs "
            "with the project root as the working directory. Stdout and "
            "stderr are combined in the result and truncated to "
            f"{_OUTPUT_CAP} characters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "Maximum seconds the command may run before being "
                        "killed. Defaults to 120."
                    ),
                    "default": 120,
                },
            },
            "required": ["command"],
        },
    },
]


def execute_shell_tool(
    name: str,
    args: dict[str, Any],
    project_root: Path,
    blocked_commands: list[str] | None = None,
) -> str:
    """Execute a shell tool and return the result.

    Args:
        name: Tool name (must be ``run_command``).
        args: Tool arguments containing ``command`` and optional ``timeout``.
        project_root: Absolute path used as the working directory.
        blocked_commands: Optional list of command prefixes or substrings
            that should be rejected for security reasons (e.g.
            ``["rm -rf /", "sudo"]``).

    Returns:
        Combined stdout/stderr output of the command, capped at
        ``_OUTPUT_CAP`` characters, or a human-readable error string.
    """
    if name != "run_command":
        return f"Error: Unknown shell tool '{name}'."

    command: str = args.get("command", "")
    timeout: int = args.get("timeout", 120)

    if not command.strip():
        return "Error: No command provided."

    # Security: reject blocked commands.
    if blocked_commands:
        cmd_lower = command.lower()
        for blocked in blocked_commands:
            if blocked.lower() in cmd_lower:
                return (
                    f"Error: Command blocked by security policy "
                    f"(matched '{blocked}')."
                )

    try:
        result = subprocess.run(
            command,
            cwd=str(project_root),
            timeout=timeout,
            capture_output=True,
            shell=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return (
            f"Error: Command timed out after {timeout}s. "
            "Consider increasing the timeout or breaking the task into "
            "smaller steps."
        )
    except Exception as exc:
        return f"Error executing command: {exc}"

    output_parts: list[str] = []
    if result.stdout:
        output_parts.append(result.stdout)
    if result.stderr:
        output_parts.append(result.stderr)

    output = "\n".join(output_parts) if output_parts else "(no output)"

    if len(output) > _OUTPUT_CAP:
        output = output[:_OUTPUT_CAP] + f"\n... (truncated at {_OUTPUT_CAP} chars)"

    # Prepend the exit code when the command failed so the agent sees it.
    if result.returncode != 0:
        output = f"[exit code {result.returncode}]\n{output}"

    return output
