"""Defensive sanitizers for adversarial / malformed upstream responses.

These exist because respx-pinned happy-path tests don't exercise hostile inputs.
Chaos testing the people-data connectors surfaced real crashes:

- a server echoing the connector's OWN api_key in an error body leaked it into
  the typed error (the pattern-based redactor can't know a custom key value);
- a non-numeric ``creditsCharged`` / ``total`` crashed ``int(...)`` / a ``<``
  comparison with ``TypeError``;
- a malformed list field (``emails`` as a dict, ``experience`` as a string)
  crashed ``model_validate`` / Pydantic construction;
- a caller passing a non-dict ``filters`` crashed ``{**filters}`` / ``dict()``.

Each helper degrades gracefully (drop/skip/None) instead of raising an
unexpected exception type, EXCEPT ``require_dict`` which raises a *typed*
``ValidationError`` for clearly-wrong caller input.
"""

from __future__ import annotations

from typing import Any, Optional, TypeVar

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from toolsconnector.errors import ValidationError

_SECRET_PLACEHOLDER = "[REDACTED]"

M = TypeVar("M", bound=BaseModel)


def safe_int(value: Any, default: int = 0) -> int:
    """Coerce any value to int; return ``default`` on failure.

    Handles str/None/garbage/bool and the JSON-decoded floats ``NaN`` /
    ``Infinity`` (Python's ``json`` accepts them) — ``int(nan)`` raises
    ``ValueError`` and ``int(inf)`` raises ``OverflowError``, both caught here.
    """
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def coerce_optional_int(value: Any) -> Optional[int]:
    """Coerce to int, or ``None`` if missing/non-numeric.

    Used for pagination totals: ``None`` cleanly disables paging instead of
    crashing a ``(page * size) < total`` comparison when the server sends a
    string/garbage/``NaN``/``Infinity`` total.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def dict_list(value: Any) -> list[dict[str, Any]]:
    """Return ``value`` only if it is a list, keeping just the dict items; else ``[]``.

    Guards Pydantic ``list[dict]`` model fields from a server sending a string
    or a list of non-dicts.
    """
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


def safe_validate(model_cls: type[M], item: Any) -> Optional[M]:
    """Validate ``item`` into ``model_cls``; return ``None`` (not raise) on bad data."""
    if not isinstance(item, dict):
        return None
    try:
        return model_cls.model_validate(item)
    except PydanticValidationError:
        return None


def validate_list(model_cls: type[M], raw: Any) -> list[M]:
    """Validate each item of ``raw`` into ``model_cls``, dropping anything malformed."""
    if not isinstance(raw, list):
        return []
    out: list[M] = []
    for item in raw:
        model = safe_validate(model_cls, item)
        if model is not None:
            out.append(model)
    return out


def require_dict(
    value: Any, field: str, *, connector: str, action: Optional[str] = None
) -> dict[str, Any]:
    """Return ``value`` if it is a dict (or ``{}`` if ``None``); else raise ValidationError.

    Turns a hostile non-dict ``filters`` into a clean typed error instead of a
    confusing ``TypeError: 'str' object is not a mapping`` from ``{**value}``.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationError(
            f"{field} must be a mapping/object, got {type(value).__name__}",
            connector=connector,
            action=action,
        )
    return value


def scrub_secret(error: Any, secret: Any) -> None:
    """Remove the connector's OWN credential value from a typed error in place.

    A misbehaving upstream can echo the api_key/token back in its error body;
    the pattern-based redactor can't recognize an arbitrary custom key, so the
    connector — which knows its own secret — scrubs it from the error's
    ``message`` and ``details`` (both of which feed ``str()`` / ``to_dict()``).
    """
    if not secret:
        return
    secret = str(secret)
    if len(secret) < 4:  # too short to redact without clobbering legitimate text
        return
    msg = getattr(error, "message", None)
    if isinstance(msg, str) and secret in msg:
        error.message = msg.replace(secret, _SECRET_PLACEHOLDER)
    details = getattr(error, "details", None)
    if isinstance(details, (dict, list)):
        _scrub_in_place(details, secret)


def _scrub_in_place(obj: Any, secret: str) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(val, str):
                if secret in val:
                    obj[key] = val.replace(secret, _SECRET_PLACEHOLDER)
            elif isinstance(val, (dict, list)):
                _scrub_in_place(val, secret)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            if isinstance(val, str):
                if secret in val:
                    obj[i] = val.replace(secret, _SECRET_PLACEHOLDER)
            elif isinstance(val, (dict, list)):
                _scrub_in_place(val, secret)
