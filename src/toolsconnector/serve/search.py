"""Tool search: find the few relevant tools instead of sending every schema.

A model pays for every tool definition on every turn, and picks worse as the
list grows. This module ranks a ToolKit's tools against a plain-language
request (BM25, standard library only) and splits execution by risk, so a host
can allow reads while still asking about deletes.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Literal, Optional

from toolsconnector.serve._filtering import ToolEntry

Risk = Literal["read", "write", "destructive"]
RISKS: tuple[Risk, ...] = ("read", "write", "destructive")

FIND_TOOL = "tc_find_tools"
RUN_TOOLS: dict[Risk, str] = {r: f"tc_run_{r}" for r in RISKS}

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
_MAX_QUERY_CHARS = 500
_DESCRIPTION_CHARS = 200
# Connector names are listed in the find tool's description up to this many;
# beyond it the list itself would become the cost this mode exists to avoid.
_MAX_LISTED_CONNECTORS = 40

_K1 = 1.2
_B = 0.75
_NAME_WEIGHT = 3
_SYNONYM_WEIGHT = 0.4

_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "to",
        "of",
        "in",
        "on",
        "for",
        "from",
        "my",
        "me",
        "with",
        "and",
        "or",
        "all",
        "is",
        "are",
        "by",
        "i",
        "at",
        "this",
        "that",
        "it",
        "as",
        "be",
    }
)
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "add": ("create",),
    "bug": ("issue",),
    "email": ("mail", "send"),
    "fetch": ("get",),
    "find": ("search", "list"),
    "mail": ("email",),
    "make": ("create",),
    "meeting": ("event",),
    "new": ("create",),
    "open": ("create",),
    "post": ("send", "create"),
    "pr": ("pull", "request"),
    "read": ("get", "list"),
    "remove": ("delete",),
    "reply": ("comment",),
    "show": ("list", "get"),
    "spreadsheet": ("sheet",),
    "ticket": ("issue",),
    "tweet": ("post", "twitter"),
}


def risk_of(entry: ToolEntry) -> Risk:
    """Return a tool's risk, treating anything undeclared as destructive."""
    if entry.dangerous or not entry.access_classified:
        return "destructive"
    if entry.access == "read":
        return "read"
    return "write" if entry.access == "write" else "destructive"


def _stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _words(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[^\W_]+", text.lower()) if w not in _STOP]


class ToolIndex:
    """In-memory BM25 index over a fixed list of tools.

    Args:
        entries: The tools to search. Only these can ever be returned.
    """

    def __init__(self, entries: list[ToolEntry]) -> None:
        self._entries = entries
        self._connectors = frozenset(e.connector_name for e in entries)
        docs = [
            Counter(
                _words(e.action_name) * _NAME_WEIGHT
                + _words(f"{e.connector_name} {e.connector_display_name}") * _NAME_WEIGHT
                + _words(" ".join(e.tags))
                + _words(e.description)
            )
            for e in entries
        ]
        lengths = [sum(d.values()) for d in docs]
        average = (sum(lengths) / len(lengths)) if lengths else 1.0
        self._postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for i, doc in enumerate(docs):
            norm = _K1 * (1 - _B + _B * lengths[i] / average)
            for word, freq in doc.items():
                self._postings[word].append((i, freq * (_K1 + 1) / (freq + norm)))

    @property
    def connectors(self) -> list[str]:
        """Sorted names of the connectors in this index."""
        return sorted(self._connectors)

    def search(
        self,
        query: str,
        *,
        connector: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[ToolEntry]:
        """Return the best-matching tools, best first.

        Args:
            query: What the caller wants to do, in plain words.
            connector: Only return tools from this connector.
            limit: Maximum results, between 1 and ``MAX_LIMIT``.

        Returns:
            Matching tools. Empty when nothing matches.
        """
        limit = max(1, min(limit, MAX_LIMIT))
        weights: dict[str, float] = {}
        for raw in re.findall(r"[^\W_]+", query[:_MAX_QUERY_CHARS].lower()):
            if raw in _STOP:
                continue
            weights[_stem(raw)] = 1.0
            for synonym in _SYNONYMS.get(raw, ()) or _SYNONYMS.get(_stem(raw), ()):
                weights.setdefault(_stem(synonym), _SYNONYM_WEIGHT)

        scores: dict[int, float] = defaultdict(float)
        total = len(self._entries)
        for word, weight in weights.items():
            postings = self._postings.get(word, ())
            idf = math.log(1 + (total - len(postings) + 0.5) / (len(postings) + 0.5))
            for i, value in postings:
                if connector is None or self._entries[i].connector_name == connector:
                    scores[i] += weight * idf * value
        # Ties break on name so the same query always returns the same order.
        ranked = sorted(scores, key=lambda i: (-scores[i], self._entries[i].tool_name))
        return [self._entries[i] for i in ranked[:limit]]


def describe_match(entry: ToolEntry) -> dict[str, Any]:
    """Render one search result: enough to call the tool, nothing more."""
    risk = risk_of(entry)
    text = " ".join(entry.description.split())
    if len(text) > _DESCRIPTION_CHARS:
        text = text[:_DESCRIPTION_CHARS].rsplit(" ", 1)[0] + " …"
    return {
        "tool": entry.tool_name,
        "description": text,
        "risk": risk,
        "run_with": RUN_TOOLS[risk],
        "input_schema": entry.input_schema or {"type": "object", "properties": {}},
    }


def search_tool_definitions(entries: list[ToolEntry]) -> list[dict[str, Any]]:
    """Describe the find tool plus one runner per risk level that is present.

    Runners with nothing to run are left out, so a read-only toolkit does not
    offer a write or destructive runner at all.

    Args:
        entries: The toolkit's tools.

    Returns:
        Dicts with ``name``, ``description``, ``input_schema`` and ``risk``.
    """
    connectors = sorted({e.connector_name for e in entries})
    if len(connectors) <= _MAX_LISTED_CONNECTORS:
        available = ", ".join(connectors)
    else:
        available = f"{len(connectors)} connectors"
    definitions: list[dict[str, Any]] = [
        {
            "name": FIND_TOOL,
            "description": (
                "Find actions for a task. Returns the best matches with their input "
                "schema and the tool to run them with. Search again with other words if "
                f"nothing fits. Available: {available}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What you want to do."},
                    "connector": {
                        "type": "string",
                        "description": "Limit to one connector, when known.",
                    },
                    "limit": {"type": "integer", "default": DEFAULT_LIMIT},
                },
                "required": ["query"],
            },
            "risk": "read",
        }
    ]
    blurbs: dict[Risk, str] = {
        "read": "Run a read-only action returned by tc_find_tools.",
        "write": "Run a write action (create or update) returned by tc_find_tools.",
        "destructive": (
            "Run an action that deletes, sends, or is not classified, returned by tc_find_tools."
        ),
    }
    present = {risk_of(e) for e in entries}
    for risk in RISKS:
        if risk in present:
            definitions.append(
                {
                    "name": RUN_TOOLS[risk],
                    "description": blurbs[risk],
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string", "description": "Name from tc_find_tools."},
                            "arguments": {"type": "object", "default": {}},
                        },
                        "required": ["tool"],
                    },
                    "risk": risk,
                }
            )
    return definitions
