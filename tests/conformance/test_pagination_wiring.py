"""Pagination-wiring ratchet.

A connector action that builds a :class:`~toolsconnector.types.PaginatedList`
with a *dynamic* ``has_more`` must also assign ``result._fetch_next``. If it
doesn't, the page advertises more results it has no way to fetch.

Since the silent-truncation fix, that combination raises
:class:`~toolsconnector.errors.PaginationNotWiredError` at runtime instead of
returning ``None`` — so the failure is loud rather than a quietly truncated
result set. Loud is much better than silent, but it is still a broken action:
``collect()`` raises where it should have returned every page.

``GRANDFATHERED_UNWIRED`` held the known unwired actions while they were fixed;
it is now empty, so the guarantee is absolute. Two tests hold the line:

* ``test_no_new_unwired_pagination`` — a new or edited action may not join the set.
* ``test_grandfathered_list_is_not_stale`` — a wired-up action must be deleted
  from the set, so it converges to empty.

A third test, ``test_fetchers_call_async_aliases``, has no baseline. Assigning
``_fetch_next`` is not enough: it must return an awaitable. Inside an action,
``self.list_x`` is the connector's *sync* wrapper, which returns a finished
``PaginatedList``, so ``await self._fetch_next()`` raises ``TypeError`` on page
two. Fetchers must call the async alias ``self.alist_x`` (or a plain
``async def`` helper). Sixteen fetchers across seven connectors shipped with
this bug before this test existed.

Detection is AST-based and deliberately **conservative**: when the ``has_more``
value cannot be proven to be the literal ``False``, the action counts as risky.
A hardcoded ``has_more=False`` (or an omitted ``has_more``, which defaults to
``False``) is never flagged — such a page is complete by construction.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
# NB: the package lives under src/, not at the repo root.
CONNECTORS_ROOT = PROJECT_ROOT / "src" / "toolsconnector" / "connectors"


def _enclosing_functions(tree: ast.AST) -> dict[ast.AST, str]:
    """Map every node to the name of its innermost enclosing function."""
    owner: dict[ast.AST, str] = {}

    def visit(node: ast.AST, current: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
            else:
                name = current
            if name is not None:
                owner[child] = name
            visit(child, name)

    visit(tree, None)
    return owner


def _has_more_is_provably_false(call: ast.Call) -> bool:
    """True when this ``PaginatedList(...)`` can never advertise another page.

    Only a literal ``has_more=False`` (or no ``has_more`` at all, which defaults
    to False) counts as proof. Anything computed — ``token is not None``,
    ``page_info.get("hasNextPage")``, a variable built earlier — is risky.
    """
    page_state = next((kw.value for kw in call.keywords if kw.arg == "page_state"), None)
    if page_state is None:
        return True  # default PageState() → has_more False
    if not (isinstance(page_state, ast.Call) and _callee_name(page_state) == "PageState"):
        return False  # built elsewhere; cannot prove it — treat as risky
    has_more = next((kw.value for kw in page_state.keywords if kw.arg == "has_more"), None)
    if has_more is None:
        return True  # PageState.has_more defaults to False
    return isinstance(has_more, ast.Constant) and has_more.value is False


def _callee_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_fetch_next_assignment(node: ast.AST) -> bool:
    """``<something>._fetch_next = ...`` (plain or annotated assignment)."""
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    return any(isinstance(t, ast.Attribute) and t.attr == "_fetch_next" for t in targets)


def _unwired_actions() -> set[str]:
    """Return ``{"<connector>.<function>"}`` for every risky-but-unwired action."""
    unwired: set[str] = set()

    for py_file in sorted(CONNECTORS_ROOT.rglob("*.py")):
        connector = py_file.relative_to(CONNECTORS_ROOT).parts[0]
        if connector.startswith("_"):
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        owner = _enclosing_functions(tree)

        risky: set[str] = set()
        wired: set[str] = set()
        for node in ast.walk(tree):
            fn = owner.get(node)
            if fn is None:
                continue
            if isinstance(node, ast.Call) and _callee_name(node) == "PaginatedList":
                if not _has_more_is_provably_false(node):
                    risky.add(fn)
            elif _is_fetch_next_assignment(node):
                wired.add(fn)

        unwired.update(f"{connector}.{fn}" for fn in risky - wired)

    return unwired


# Baseline captured 2026-09-19 at 88 unwired actions across 30 connectors; all of
# them were wired by 2026-09-23, so this is now empty and the ratchet is a HARD
# guarantee: no action may build a PaginatedList with a dynamic has_more and no
# fetcher. Do not repopulate it. Wire `result._fetch_next` instead (see
# connectors/gitlab or connectors/shopify for the idiom).
GRANDFATHERED_UNWIRED: frozenset[str] = frozenset()


def test_no_new_unwired_pagination() -> None:
    """A new or edited action may not ship a dynamic has_more without a fetcher."""
    new_unwired = _unwired_actions() - GRANDFATHERED_UNWIRED
    assert not new_unwired, (
        "Action(s) building a PaginatedList with a dynamic `has_more` but no "
        "`result._fetch_next`. Page two is unreachable and `collect()` raises "
        "PaginationNotWiredError. Assign `result._fetch_next` before returning "
        "(pass the next cursor through as a lambda default):\n  " + "\n  ".join(sorted(new_unwired))
    )


def test_grandfathered_list_is_not_stale() -> None:
    """Wired-up actions must be dropped from the baseline so it converges to empty."""
    stale = GRANDFATHERED_UNWIRED - _unwired_actions()
    assert not stale, (
        "These now wire `_fetch_next` — delete them from GRANDFATHERED_UNWIRED "
        "to keep the ratchet tight:\n  " + "\n  ".join(sorted(stale))
    )


def _is_action(fn: ast.AST) -> bool:
    """True for an ``@action``-decorated method (the runtime sync-wraps these)."""
    for deco in getattr(fn, "decorator_list", []):
        target = deco.func if isinstance(deco, ast.Call) else deco
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if name == "action":
            return True
    return False


def _sync_wrapper_fetchers() -> set[str]:
    """``{"<connector>.<function> -> self.<name>"}`` for fetchers that call a sync wrapper."""
    bad: set[str] = set()
    for py_file in sorted(CONNECTORS_ROOT.rglob("*.py")):
        connector = py_file.relative_to(CONNECTORS_ROOT).parts[0]
        if connector.startswith("_"):
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        actions = {n.name for n in ast.walk(tree) if _is_action(n)}
        owner = _enclosing_functions(tree)
        for node in ast.walk(tree):
            if not _is_fetch_next_assignment(node):
                continue
            for sub in ast.walk(node.value):  # type: ignore[attr-defined]
                if not (isinstance(sub, ast.Lambda) and isinstance(sub.body, ast.Call)):
                    continue
                func = sub.body.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "self"
                    and func.attr in actions
                ):
                    bad.add(f"{connector}.{owner.get(node, '?')} -> self.{func.attr}")
    return bad


def test_fetchers_call_async_aliases() -> None:
    """A fetcher must return an awaitable, so it must call ``self.a<action>``."""
    bad = _sync_wrapper_fetchers()
    assert not bad, (
        "`_fetch_next` calls a sync action wrapper, so `anext_page()` raises "
        "TypeError on page two. Call the async alias instead "
        "(`self.alist_x`, not `self.list_x`):\n  " + "\n  ".join(sorted(bad))
    )
