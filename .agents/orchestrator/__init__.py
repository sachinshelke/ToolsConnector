"""ToolsConnector Agent Army Orchestrator.

Autonomous DAG-based task executor powered by Claude Agent SDK.
Reads a task board, resolves dependencies, and dispatches specialized
Claude agents in parallel to build the project.

Usage:
    python -m agents.orchestrator run --phase 0
    python -m agents.orchestrator run --phase 0 --dry-run
    python -m agents.orchestrator status
"""
