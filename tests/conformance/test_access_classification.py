"""Tier-1 access-classification ratchet.

Every action on a Tier-1 (``verification_status == "live"``) connector must
declare a positive read/write/destructive ``access`` classification
(``spec/action.py`` ``AccessKind``), so a consumer enforcing read-only has a
*contract* instead of a naming heuristic (``dangerous`` is a destructive flag
only, not a read/write one). ``dangerous`` auto-derives ``access="destructive"``
in the ``@action`` decorator, and the two must always agree.

Non-Tier-1 actions may still be ``None`` (unclassified) — a read-only consumer
treats ``None`` as "not provably read" and fails closed. This ratchet holds the
line at 100% for the connectors consumers trust most.
"""

from __future__ import annotations

import re

from toolsconnector.serve import list_connectors
from toolsconnector.serve._discovery import get_connector_class

_VALID = {"read", "write", "destructive"}


def _tier1_actions():
    for name in list_connectors():
        cls = get_connector_class(name)
        if getattr(cls, "verification_status", None) != "live":
            continue
        for action_name, spec in cls.get_spec().actions.items():
            yield name, action_name, spec


def test_every_tier1_action_is_classified() -> None:
    """No Tier-1 action may ship without a read/write/destructive access value."""
    missing = [f"{c}.{a}" for c, a, s in _tier1_actions() if s.access is None]
    assert not missing, (
        "Tier-1 action(s) with no `access` classification — declare "
        'access="read"/"write" on the @action (or dangerous=True, which '
        "auto-classifies destructive):\n  " + "\n  ".join(sorted(missing))
    )


def test_tier1_access_values_are_valid() -> None:
    bad = [
        f"{c}.{a}={s.access!r}"
        for c, a, s in _tier1_actions()
        if s.access is not None and s.access not in _VALID
    ]
    assert not bad, "Invalid access values (expect read|write|destructive):\n  " + "\n  ".join(
        sorted(bad)
    )


def test_destructive_iff_dangerous_catalog_wide() -> None:
    """``access == "destructive"`` and ``dangerous`` describe the same property,
    so they must agree for EVERY action across all connectors (not just Tier-1)."""
    violations = []
    for name in list_connectors():
        for a, s in get_connector_class(name).get_spec().actions.items():
            if (s.access == "destructive") != s.dangerous:
                violations.append(f"{name}.{a} access={s.access!r} dangerous={s.dangerous}")
    assert not violations, "access=='destructive' must iff dangerous:\n  " + "\n  ".join(
        sorted(violations)
    )


# Verbs whose effect can't be undone through the same API. ``trash``/``archive``
# are left out: they are reversible wherever they appear in Tier 1.
_IRREVERSIBLE = re.compile(
    r"(^|_)(delete|unlink|purge|destroy|cancel|revoke|terminate|refund)(_|$)"
)

# Not irreversible despite the name, with the reason.
_IRREVERSIBLE_EXEMPT: dict[str, str] = {}


def test_irreversible_verbs_are_destructive() -> None:
    """A delete declared ``access="write"`` is published to MCP clients as
    ``destructiveHint: false``, so a client may run it without asking.
    ``odoo.unlink`` and ``stripe.cancel_payment_intent`` shipped that way."""
    bad = [
        f"{c}.{a} access={s.access!r}"
        for c, a, s in _tier1_actions()
        if _IRREVERSIBLE.search(a)
        and not s.dangerous
        and s.access != "read"
        and f"{c}.{a}" not in _IRREVERSIBLE_EXEMPT
    ]
    assert not bad, "irreversible action(s) not marked dangerous=True:\n  " + "\n  ".join(bad)


def test_escape_hatch_is_destructive() -> None:
    """``odoo.call_method`` runs any model method, including deletes."""
    call = [s for c, a, s in _tier1_actions() if (c, a) == ("odoo", "call_method")]
    assert call and call[0].access == "destructive"
