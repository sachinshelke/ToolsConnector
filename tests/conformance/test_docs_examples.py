"""Documented examples must match the real API.

0.4.0 shipped a README whose first example raised ``TypeError`` (``max_results``
is not a parameter of ``gmail_list_emails``), guides that passed ``ToolKit``
options that don't exist, and 42 credential samples in a shape the connector
rejects. Every fenced Python block and ``tc`` line in the docs is checked
against the code: imports, constructor options, tool names, argument names and
credential shapes. Nothing is executed and no request is sent.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from toolsconnector.serve import ToolKit, ToolKitFactory, list_connectors

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted(
    [ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "examples" / "README.md"]
    + list((ROOT / "docs").rglob("*.md"))
    + list((ROOT / "src/toolsconnector/connectors").glob("*/README.md"))
)
_SERVE_MCP_FLAGS = {"transport", "host", "port", "name", "help"}


@pytest.fixture(scope="module")
def kit() -> ToolKit:
    return ToolKit(list_connectors())


def _blocks() -> Iterator[tuple[str, ast.AST]]:
    """Yield ``(location, tree)`` for every Python block that parses.

    Signature listings such as ``ToolKit(connectors: list[str], ...)`` are not
    valid Python and are skipped; ``test_blocks_are_scanned`` bounds that.
    """
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^( *)```(?:python|py)\n(.*?)^ *```", text, re.M | re.S):
            where = f"{path.relative_to(ROOT)}:{text[: m.start()].count(chr(10)) + 1}"
            code = textwrap.dedent(m[2])
            for source in (code, "async def _():\n" + textwrap.indent(code, "    ")):
                try:
                    yield where, ast.parse(source)
                except SyntaxError:
                    continue
                break


def _calls(tree: ast.AST) -> Iterator[ast.Call]:
    return (n for n in ast.walk(tree) if isinstance(n, ast.Call))


def _report(problems: list[str]) -> None:
    assert not problems, f"{len(problems)} documented example(s) are wrong:\n  " + "\n  ".join(
        sorted(set(problems))
    )


def test_blocks_are_scanned() -> None:
    """The checks below must not pass by scanning nothing."""
    assert len(list(_blocks())) > 300


def test_imports_resolve() -> None:
    problems = []
    for where, tree in _blocks():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ImportFrom) and node.module):
                continue
            if node.module.split(".")[0] != "toolsconnector":
                continue
            try:
                module = importlib.import_module(node.module)
            except ImportError as exc:
                problems.append(f"{where} {exc}")
                continue
            problems += [
                f"{where} {node.module} has no {a.name}"
                for a in node.names
                if a.name != "*" and not hasattr(module, a.name)
            ]
    _report(problems)


def test_toolkit_options_exist() -> None:
    allowed = {
        "ToolKit": set(inspect.signature(ToolKit).parameters),
        "ToolKitFactory": set(inspect.signature(ToolKitFactory).parameters),
    }
    for method in ("execute", "aexecute", "serve_mcp", "create_rest_app"):
        allowed[method] = set(inspect.signature(getattr(ToolKit, method)).parameters)
    problems = []
    for where, tree in _blocks():
        for call in _calls(tree):
            f = call.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            if isinstance(f, ast.Attribute) and not (
                isinstance(f.value, ast.Name) and f.value.id in ("kit", "toolkit")
            ):
                continue
            if isinstance(f, ast.Attribute) and not hasattr(ToolKit, name):
                problems.append(f"{where} ToolKit.{name}() does not exist")
            problems += [
                f"{where} {name}() has no option {kw.arg!r}"
                for kw in call.keywords
                if kw.arg and name in allowed and kw.arg not in allowed[name]
            ]
    _report(problems)


def _arguments(node: ast.Dict) -> tuple[set[str], bool]:
    keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
    elided = None in node.keys or any(
        isinstance(v, ast.Constant) and v.value is Ellipsis for v in node.values
    )
    return keys, elided


def test_tool_calls_match_schemas(kit: ToolKit) -> None:
    problems = []
    for where, tree in _blocks():
        for call in _calls(tree):
            if getattr(call.func, "attr", "") not in ("execute", "aexecute") or not call.args:
                continue
            first = call.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            entry = kit._tool_entries.get(first.value)
            if entry is None:
                problems.append(f"{where} no tool {first.value!r}")
                continue
            if len(call.args) < 2 or not isinstance(call.args[1], ast.Dict):
                continue
            keys, elided = _arguments(call.args[1])
            known = set(entry.input_schema.get("properties", {}))
            missing = set(entry.input_schema.get("required") or []) - keys
            if keys - known:
                problems.append(f"{where} {first.value} has no {sorted(keys - known)}")
            if missing and keys and not elided:
                problems.append(f"{where} {first.value} needs {sorted(missing)}")
    _report(problems)


def _shape_problem(contract: dict[str, Any], value: Any) -> str | None:
    if contract["credential_format"] == "delimited":
        sep, order = contract.get("separator", ":"), contract["order"]
        if not isinstance(value, str) or value.count(sep) < len(order) - 1:
            return "needs " + sep.join(f"<{o}>" for o in order)
    elif contract["credential_format"] == "string" and not isinstance(value, str):
        return "needs a string"
    return None


def test_credential_samples_have_the_declared_shape(kit: ToolKit) -> None:
    problems = []
    for where, tree in _blocks():
        for call in _calls(tree):
            for kw in call.keywords:
                if kw.arg != "credentials" or not isinstance(kw.value, ast.Dict):
                    continue
                for key, node in zip(kw.value.keys, kw.value.values, strict=True):
                    cls = kit._connector_classes.get(getattr(key, "value", None) or "")
                    try:
                        value = ast.literal_eval(node)
                    except ValueError:
                        continue
                    if cls is None or value is Ellipsis:
                        continue
                    supported = cls._build_auth_spec().supported
                    problem = supported and _shape_problem(supported[0].extra, value)
                    if problem:
                        problems.append(f"{where} {cls.name}: {problem}")
    _report(problems)


def test_cli_lines_match(kit: ToolKit) -> None:
    problems = []
    for path in DOCS:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{path.relative_to(ROOT)}:{number}"
            served = re.search(r"tc serve mcp ([^#`|]*)", line)
            if served:
                flags = set(re.findall(r"--([a-z-]+)", served[1]))
                problems += [f"{where} tc serve mcp has no --{f}" for f in flags - _SERVE_MCP_FLAGS]
            run = re.match(r"\s*tc ([a-z0-9_]+) ([a-z0-9_]+)(.*)", line)
            if not run or run[1] == "serve" or run[2] in ("actions", "spec"):
                continue
            entry = kit._tool_entries.get(f"{run[1]}_{run[2]}")
            if entry is None:
                problems.append(f"{where} tc {run[1]} has no action {run[2]}")
                continue
            unknown = set(re.findall(r"--([a-z_]+)", run[3])) - set(
                entry.input_schema.get("properties", {})
            )
            problems += [f"{where} {entry.tool_name} has no --{u}" for u in unknown]
    _report(problems)


def test_documented_signatures_match() -> None:
    """``docs/API.md`` lists constructor options in order."""
    text = (ROOT / "docs/API.md").read_text(encoding="utf-8")
    for cls in (ToolKit, ToolKitFactory):
        block = re.search(rf"^{cls.__name__}\(\n(.*?)^\)", text, re.M | re.S)
        assert block, f"docs/API.md has no {cls.__name__} signature"
        documented = re.findall(r"^    (\w+):", block[1], re.M)
        assert documented == list(inspect.signature(cls).parameters)
