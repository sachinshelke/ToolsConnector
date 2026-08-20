"""Tier-1 docstring-quality ratchet.

The serve layer publishes each action's docstring prose to LLM callers
(``serve/_filtering.py::_build_description``). A *thin* docstring — prose that
merely restates the ``@action`` title with no syntax, example, value format, or
gotcha — publishes nothing a model can act on, which produces wrong or
destructive calls (see the gdrive ``search_files`` HTTP-400 case).

This ratchet freezes the set of *known* thin Tier-1 (``verification_status ==
"live"``) actions and asserts the live set never grows beyond it:

* ``test_no_new_thin_tier1_docstrings`` — a new or edited Tier-1 action may not
  ship a thin docstring (the set can only shrink).
* ``test_grandfathered_list_is_not_stale`` — once an action is enriched it must
  be removed from ``GRANDFATHERED_THIN``, so the list tightens toward empty.

When ``GRANDFATHERED_THIN`` reaches ``frozenset()`` this becomes a hard
"no thin Tier-1 docstrings" guarantee. See memory ``project_docstring_publishing``.
"""

from __future__ import annotations

import re

from toolsconnector.runtime.action import _extract_docstring_prose
from toolsconnector.serve import list_connectors
from toolsconnector.serve._discovery import get_connector_class

# A "contract marker": backticks / rst-directive / example / URL / year / path /
# HTTP-verb semantics / base64 — the signals that a docstring says something a
# caller couldn't infer from the title alone.
_MARKER = re.compile(r"``|::|e\.g\.|example|\bhttp|\d{4}|/|\bPUT\b|\bPATCH\b|base64", re.I)


def _is_thin(title: str, prose: str) -> bool:
    """Thin = prose barely exceeds the title AND carries no contract marker.

    Heuristic, and deliberately advisory: the length path (prose longer than the
    title) clears the gate without a marker, so a determined author *could* pass
    a padded restatement carrying no real contract. Requiring a marker
    unconditionally was measured to misclassify ~180 legitimately-documented
    Tier-1 actions as thin, so this stays a backstop against lazy
    title-restatement regressions — genuine quality is enforced by authors and
    review, not by this classifier alone.
    """
    if not prose:
        return True
    barely_longer = len(prose) <= max(len(title) + 10, int(1.2 * len(title)))
    return barely_longer and not _MARKER.search(prose)


def _tier1_thin() -> set[str]:
    """Set of ``{connector}.{action}`` for thin-docstring Tier-1 actions."""
    thin: set[str] = set()
    for name in list_connectors():
        cls = get_connector_class(name)
        if getattr(cls, "verification_status", None) != "live":
            continue
        for attr in dir(cls):
            fn = getattr(cls, attr, None)
            meta = getattr(fn, "__action_meta__", None)
            if meta is None:
                continue
            title = meta.description or ""
            # Same prose the serve layer publishes — single source of truth.
            if _is_thin(title, _extract_docstring_prose(fn, title)):
                thin.add(f"{name}.{meta.name}")
    return thin


# All Tier-1 docstrings now carry a real usage contract (enriched 2026-08-02),
# so this is empty and the ratchet is a HARD guarantee: no Tier-1 action may
# ship a thin docstring. When adding or editing a Tier-1 action, write a proper
# contract docstring (see docs/guides/adding-connector.md) — do not repopulate it.
GRANDFATHERED_THIN: frozenset[str] = frozenset()


def test_no_new_thin_tier1_docstrings() -> None:
    """No Tier-1 action outside the grandfathered set may have a thin docstring."""
    new_thin = _tier1_thin() - GRANDFATHERED_THIN
    assert not new_thin, (
        "Tier-1 action(s) with a thin docstring (title restated, no usage "
        "contract). Add a paragraph with syntax / an example / a value format / "
        "a gotcha to the docstring prose above ``Args:``:\n  " + "\n  ".join(sorted(new_thin))
    )


def test_grandfathered_list_is_not_stale() -> None:
    """Enriched actions must be dropped from GRANDFATHERED_THIN so it converges."""
    stale = GRANDFATHERED_THIN - _tier1_thin()
    assert not stale, (
        "These are no longer thin — delete them from GRANDFATHERED_THIN to keep "
        "the ratchet tight:\n  " + "\n  ".join(sorted(stale))
    )
