"""Orchestrator configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SandboxConfig:
    """Security sandbox for agent file/command access."""

    allowed_dirs: list[str] = field(default_factory=lambda: [
        "toolsconnector/",
        "tests/",
        "pyproject.toml",
        ".agents/skills/",
    ])
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /",
        "git push --force",
        "pip install --user",
    ])
    require_git_branch: bool = True


@dataclass
class OrchestratorConfig:
    """Top-level orchestrator configuration."""

    # API
    api_key: str = ""
    default_model: str = "claude-sonnet-4-6"
    model_overrides: dict[str, str] = field(default_factory=lambda: {
        "principal-architect": "claude-sonnet-4-6",
        "reviewer": "claude-sonnet-4-6",
    })

    # Execution
    max_parallel: int = 4
    default_timeout: int = 3600  # seconds
    working_branch_prefix: str = "agent/"

    # Paths
    project_root: Path = field(default_factory=lambda: Path.cwd())
    taskboard_path: Path = field(
        default_factory=lambda: Path(".agents/taskboard.yaml")
    )
    log_dir: Path = field(default_factory=lambda: Path(".agents/logs"))
    state_db_path: Path = field(default_factory=lambda: Path(".agents/state.db"))
    skills_dir: Path = field(default_factory=lambda: Path(".agents/skills"))

    # Safety
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)

    def get_model_for_agent(self, agent_type: str) -> str:
        """Return the model to use for a given agent type."""
        return self.model_overrides.get(agent_type, self.default_model)

    @classmethod
    def load(cls, config_path: Path | None = None) -> OrchestratorConfig:
        """Load config from YAML file, env vars, or defaults."""
        config_data: dict[str, Any] = {}

        # Load from file if exists
        if config_path and config_path.exists():
            with open(config_path) as f:
                raw = yaml.safe_load(f)
                if raw and "orchestrator" in raw:
                    config_data = raw["orchestrator"]

        # API key from env (always overrides file)
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            api_key = config_data.get("api_key_env", "")
            if api_key:
                api_key = os.environ.get(api_key, "")

        # Build config
        sandbox_data = config_data.get("sandbox", {})
        defaults = SandboxConfig()
        sandbox = SandboxConfig(
            allowed_dirs=sandbox_data.get("allowed_dirs", defaults.allowed_dirs),
            blocked_commands=sandbox_data.get(
                "blocked_commands", defaults.blocked_commands
            ),
            require_git_branch=sandbox_data.get("require_git_branch", True),
        )

        return cls(
            api_key=api_key,
            default_model=config_data.get("model", cls.default_model),
            model_overrides=config_data.get("model_overrides", {}),
            max_parallel=config_data.get("max_parallel", 4),
            default_timeout=config_data.get("default_timeout", 3600),
            working_branch_prefix=config_data.get(
                "working_branch_prefix", "agent/"
            ),
            log_dir=Path(config_data.get("log_dir", ".agents/logs")),
            state_db_path=Path(config_data.get("state_db", ".agents/state.db")),
            sandbox=sandbox,
        )
