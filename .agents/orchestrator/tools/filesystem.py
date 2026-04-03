"""Filesystem tools for agent sessions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

FILESYSTEM_TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file. Returns the full file content. "
            "Use this to understand existing code before modifying it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative file path from project root.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file, creating it if it doesn't exist. "
            "Overwrites existing content. Use for creating new files or "
            "complete rewrites."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative file path from project root.",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Edit a file by replacing an exact string match with new content. "
            "The old_string must match exactly (including whitespace). "
            "Prefer this over write_file for modifying existing files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative file path from project root.",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact string to find and replace.",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement string.",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List files matching a glob pattern. Returns relative paths. "
            "Example: '**/*.py' for all Python files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: project root).",
                    "default": ".",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "search_files",
        "description": (
            "Search file contents using a regex pattern. Returns matching "
            "lines with file paths and line numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in.",
                    "default": ".",
                },
                "file_glob": {
                    "type": "string",
                    "description": "File pattern to filter (e.g., '*.py').",
                    "default": "*",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a directory (and parents) if it doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path to create.",
                },
            },
            "required": ["path"],
        },
    },
]


def execute_filesystem_tool(
    name: str,
    args: dict[str, Any],
    project_root: Path,
    allowed_dirs: list[str],
) -> str:
    """Execute a filesystem tool and return the result."""
    rel_path = args.get("path", ".")
    abs_path = (project_root / rel_path).resolve()

    # Security: check path is within project
    if not str(abs_path).startswith(str(project_root.resolve())):
        return f"Error: Path '{rel_path}' is outside the project directory."

    if name == "read_file":
        if not abs_path.exists():
            return f"Error: File '{rel_path}' does not exist."
        if abs_path.is_dir():
            return f"Error: '{rel_path}' is a directory, not a file."
        try:
            return abs_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"

    elif name == "write_file":
        content = args.get("content", "")
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        return f"File '{rel_path}' written successfully ({len(content)} chars)."

    elif name == "edit_file":
        if not abs_path.exists():
            return f"Error: File '{rel_path}' does not exist."
        old = args.get("old_string", "")
        new = args.get("new_string", "")
        text = abs_path.read_text(encoding="utf-8")
        if old not in text:
            return f"Error: old_string not found in '{rel_path}'."
        if text.count(old) > 1:
            return (
                f"Error: old_string found {text.count(old)} times in "
                f"'{rel_path}'. Provide more context to make it unique."
            )
        updated = text.replace(old, new, 1)
        abs_path.write_text(updated, encoding="utf-8")
        return f"File '{rel_path}' edited successfully."

    elif name == "list_files":
        pattern = args.get("pattern", "*")
        search_path = (project_root / args.get("path", ".")).resolve()
        if not search_path.exists():
            return f"Error: Directory '{args.get('path', '.')}' does not exist."
        matches = sorted(search_path.glob(pattern))
        rel_matches = []
        for m in matches[:200]:  # Limit results
            try:
                rel_matches.append(str(m.relative_to(project_root)))
            except ValueError:
                continue
        if not rel_matches:
            return f"No files matching '{pattern}' found."
        return "\n".join(rel_matches)

    elif name == "search_files":
        import re
        pattern_str = args.get("pattern", "")
        search_dir = (project_root / args.get("path", ".")).resolve()
        file_glob = args.get("file_glob", "*.py")
        try:
            regex = re.compile(pattern_str)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"
        results = []
        for fpath in sorted(search_dir.rglob(file_glob)):
            if fpath.is_dir():
                continue
            try:
                lines = fpath.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines, 1):
                    if regex.search(line):
                        rel = str(fpath.relative_to(project_root))
                        results.append(f"{rel}:{i}: {line.strip()}")
            except (UnicodeDecodeError, PermissionError):
                continue
            if len(results) >= 100:
                break
        if not results:
            return f"No matches found for pattern '{pattern_str}'."
        return "\n".join(results)

    elif name == "create_directory":
        abs_path.mkdir(parents=True, exist_ok=True)
        return f"Directory '{rel_path}' created."

    return f"Error: Unknown filesystem tool '{name}'."
