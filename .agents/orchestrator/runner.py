"""Agent runner — spawns Claude sessions via Anthropic API.

Each agent is a multi-turn conversation with tool access.
The runner manages the conversation loop until the agent
completes its task or hits a timeout.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from .tools.filesystem import FILESYSTEM_TOOLS, execute_filesystem_tool
from .tools.shell import SHELL_TOOLS, execute_shell_tool
from .tools.git import GIT_TOOLS, execute_git_tool
from .tools.test import TEST_TOOLS, execute_test_tool
from .state import StateManager

logger = logging.getLogger(__name__)

# Build the combined tool list once at import time.
ALL_TOOLS: list[dict[str, Any]] = [
    *FILESYSTEM_TOOLS,
    *SHELL_TOOLS,
    *GIT_TOOLS,
    *TEST_TOOLS,
]

# Sets of tool names for fast dispatch routing.
_FS_TOOLS = {t["name"] for t in FILESYSTEM_TOOLS}
_SHELL_TOOLS = {t["name"] for t in SHELL_TOOLS}
_GIT_TOOLS = {t["name"] for t in GIT_TOOLS}
_TEST_TOOLS = {t["name"] for t in TEST_TOOLS}

# Maximum characters to keep for tool result logging.
_LOG_TRUNCATE = 2000

# Approximate pricing in cents per 1K tokens.
# Updated as of 2025-Q4; add new entries as models are released.
_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 0.3, "output": 1.5},
    "claude-opus-4-6": {"input": 1.5, "output": 7.5},
    "claude-haiku-4-5-20251001": {"input": 0.08, "output": 0.4},
}
_DEFAULT_PRICING = _PRICING["claude-sonnet-4-6"]


@dataclass
class TaskResult:
    """Result of an agent task execution."""

    success: bool
    output: str = ""
    error: str | None = None
    token_input: int = 0
    token_output: int = 0
    cost_cents: float = 0.0
    duration_seconds: float = 0.0
    files_changed: list[str] = field(default_factory=list)
    turns_used: int = 0


class AgentRunner:
    """Spawns and manages Claude agent sessions.

    The runner owns the conversation loop: it sends the task prompt to
    Claude, executes any requested tool calls, feeds results back, and
    repeats until the model emits ``end_turn`` or a hard limit is hit.
    """

    def __init__(
        self,
        api_key: str,
        project_root: Path,
        state: StateManager,
        allowed_dirs: list[str] | None = None,
        blocked_commands: list[str] | None = None,
    ) -> None:
        self.client = anthropic.Anthropic(api_key=api_key)
        self.project_root = project_root.resolve()
        self.state = state
        self.allowed_dirs = allowed_dirs or []
        self.blocked_commands = blocked_commands or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_task(
        self,
        task_id: str,
        system_prompt: str,
        task_prompt: str,
        model: str = "claude-sonnet-4-6",
        max_turns: int = 100,
        timeout: int = 3600,
        phase: int = 0,
        agent_type: str = "unknown",
    ) -> TaskResult:
        """Run a single agent task to completion.

        The agent loop:
        1. Send task prompt to Claude with system prompt + tools.
        2. Claude responds with tool calls or text.
        3. Execute tool calls (file ops, shell, git, tests).
        4. Feed results back to Claude.
        5. Repeat until Claude finishes (``end_turn``) or a hard limit
           (timeout / max_turns) is reached.

        Returns a :class:`TaskResult` regardless of outcome so the
        caller never needs to handle exceptions from this method.
        """
        # Record the run in the state DB.
        task_run_id = self.state.start_task_run(
            task_id=task_id,
            phase=phase,
            agent_type=agent_type,
            model=model,
        )

        start_time = time.monotonic()
        total_input_tokens = 0
        total_output_tokens = 0
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": task_prompt},
        ]

        try:
            for turn in range(max_turns):
                # ---- Timeout check --------------------------------
                elapsed = time.monotonic() - start_time
                if elapsed > timeout:
                    return self._finish(
                        task_run_id,
                        start_time,
                        total_input_tokens,
                        total_output_tokens,
                        model,
                        status="timeout",
                        error=f"Timeout after {int(elapsed)}s ({turn} turns)",
                        turns=turn,
                    )

                # ---- Call Claude ----------------------------------
                try:
                    response = self.client.messages.create(
                        model=model,
                        max_tokens=16384,
                        system=system_prompt,
                        tools=ALL_TOOLS,
                        messages=messages,
                    )
                except anthropic.APIConnectionError as exc:
                    logger.warning("API connection error on turn %d: %s", turn, exc)
                    return self._finish(
                        task_run_id, start_time,
                        total_input_tokens, total_output_tokens, model,
                        status="failed",
                        error=f"APIConnectionError: {exc}",
                        turns=turn,
                    )
                except anthropic.RateLimitError as exc:
                    # Back off and retry once; if it still fails, bail.
                    logger.warning("Rate limited on turn %d, backing off", turn)
                    time.sleep(min(30, 2 ** min(turn, 5)))
                    try:
                        response = self.client.messages.create(
                            model=model,
                            max_tokens=16384,
                            system=system_prompt,
                            tools=ALL_TOOLS,
                            messages=messages,
                        )
                    except anthropic.APIError as retry_exc:
                        return self._finish(
                            task_run_id, start_time,
                            total_input_tokens, total_output_tokens, model,
                            status="failed",
                            error=f"RateLimitError (retry failed): {retry_exc}",
                            turns=turn,
                        )
                except anthropic.APIStatusError as exc:
                    logger.error("API status error on turn %d: %s", turn, exc)
                    return self._finish(
                        task_run_id, start_time,
                        total_input_tokens, total_output_tokens, model,
                        status="failed",
                        error=f"APIStatusError({exc.status_code}): {exc.message}",
                        turns=turn,
                    )

                # ---- Track tokens ---------------------------------
                total_input_tokens += response.usage.input_tokens
                total_output_tokens += response.usage.output_tokens

                # ---- Log assistant text ---------------------------
                assistant_text = self._extract_text(response.content)
                if assistant_text:
                    self.state.log_agent_message(
                        task_run_id,
                        role="assistant",
                        content=assistant_text[:_LOG_TRUNCATE],
                    )

                # ---- end_turn: task completed ---------------------
                if response.stop_reason == "end_turn":
                    return self._finish(
                        task_run_id, start_time,
                        total_input_tokens, total_output_tokens, model,
                        status="completed",
                        output=assistant_text,
                        turns=turn + 1,
                    )

                # ---- max_tokens: model ran out of room ------------
                if response.stop_reason == "max_tokens":
                    logger.warning(
                        "Model hit max_tokens on turn %d, treating as done", turn,
                    )
                    return self._finish(
                        task_run_id, start_time,
                        total_input_tokens, total_output_tokens, model,
                        status="completed",
                        output=assistant_text,
                        turns=turn + 1,
                    )

                # ---- tool_use: execute tools ----------------------
                if response.stop_reason == "tool_use":
                    # Append the full assistant message (text + tool_use blocks).
                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                    })

                    tool_results: list[dict[str, Any]] = []
                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        tool_output = self._execute_tool(
                            block.name, block.input,
                        )

                        # Log every tool invocation.
                        self.state.log_agent_message(
                            task_run_id,
                            role="tool",
                            content=tool_output[:_LOG_TRUNCATE],
                            tool_name=block.name,
                            tool_input=json.dumps(
                                block.input, default=str,
                            )[:_LOG_TRUNCATE],
                            tool_output=tool_output[:_LOG_TRUNCATE],
                        )

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_output,
                        })

                    messages.append({
                        "role": "user",
                        "content": tool_results,
                    })
                    continue

                # ---- Unexpected stop reason -----------------------
                logger.warning(
                    "Unexpected stop_reason '%s' on turn %d",
                    response.stop_reason, turn,
                )
                return self._finish(
                    task_run_id, start_time,
                    total_input_tokens, total_output_tokens, model,
                    status="failed",
                    error=f"Unexpected stop_reason: {response.stop_reason}",
                    output=assistant_text,
                    turns=turn + 1,
                )

            # ---- Exceeded max turns -----------------------------------
            return self._finish(
                task_run_id, start_time,
                total_input_tokens, total_output_tokens, model,
                status="failed",
                error=f"Exceeded max turns ({max_turns})",
                turns=max_turns,
            )

        except Exception as exc:
            logger.exception("Unhandled error during agent run")
            return self._finish(
                task_run_id, start_time,
                total_input_tokens, total_output_tokens, model,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                turns=0,
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _finish(
        self,
        task_run_id: int,
        start_time: float,
        input_tokens: int,
        output_tokens: int,
        model: str,
        *,
        status: str,
        error: str | None = None,
        output: str = "",
        turns: int = 0,
    ) -> TaskResult:
        """Build a :class:`TaskResult` and persist the run outcome."""
        duration = time.monotonic() - start_time
        cost = self._estimate_cost(input_tokens, output_tokens, model)
        success = status == "completed"

        self.state.complete_task_run(
            task_run_id,
            status,
            error=error,
            token_input=input_tokens,
            token_output=output_tokens,
            cost_cents=cost,
        )

        return TaskResult(
            success=success,
            output=output,
            error=error,
            token_input=input_tokens,
            token_output=output_tokens,
            cost_cents=cost,
            duration_seconds=duration,
            turns_used=turns,
        )

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Route a tool call to the appropriate executor.

        Every executor is expected to return a plain string — never
        raise.  If an executor does raise, we catch and return an
        error string so the agent can recover.
        """
        try:
            if name in _FS_TOOLS:
                return execute_filesystem_tool(
                    name, args, self.project_root, self.allowed_dirs,
                )

            if name in _SHELL_TOOLS:
                return execute_shell_tool(
                    name, args, self.project_root, self.blocked_commands,
                )

            if name in _GIT_TOOLS:
                return execute_git_tool(name, args, self.project_root)

            if name in _TEST_TOOLS:
                # execute_test_tool expects project_root as str.
                return execute_test_tool(
                    name, args, str(self.project_root),
                )

            return f"Error: Unknown tool '{name}'"
        except Exception as exc:
            logger.exception("Tool '%s' raised an exception", name)
            return f"Error executing tool '{name}': {type(exc).__name__}: {exc}"

    @staticmethod
    def _extract_text(content: list[Any]) -> str:
        """Extract text content from response blocks."""
        parts: list[str] = []
        for block in content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts)

    @staticmethod
    def _estimate_cost(
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> float:
        """Estimate cost in cents based on model pricing."""
        rates = _PRICING.get(model, _DEFAULT_PRICING)
        return (
            (input_tokens / 1000) * rates["input"]
            + (output_tokens / 1000) * rates["output"]
        )
