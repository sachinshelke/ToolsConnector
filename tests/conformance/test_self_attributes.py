"""Every ``self.<name>`` a connector uses must exist.

Seven published actions called helpers that were never defined, so they raised
``AttributeError`` on every call. Nothing ran them, so nothing noticed.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from toolsconnector.serve import list_connectors
from toolsconnector.serve._discovery import get_connector_class


@pytest.mark.parametrize("name", list_connectors())
def test_self_attributes_exist(name: str) -> None:
    cls = get_connector_class(name)
    known = set(dir(cls))
    actions = set(cls.get_spec().actions)
    known |= actions | {f"a{a}" for a in actions}
    used: dict[str, set[str]] = {}
    for klass in cls.__mro__:
        if not klass.__module__.startswith("toolsconnector."):
            continue
        for fn in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(klass)))):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                ):
                    if isinstance(node.ctx, ast.Store):
                        known.add(node.attr)
                    else:
                        used.setdefault(node.attr, set()).add(fn.name)
    missing = {attr: sorted(fns) for attr, fns in used.items() if attr not in known}
    assert not missing
