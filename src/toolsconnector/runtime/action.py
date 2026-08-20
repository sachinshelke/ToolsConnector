"""The @action decorator — the heart of ToolsConnector.

Marks a connector method as an externally-callable action. At class
definition time, the decorator:

1. Parses the method's type hints to build a Pydantic input model.
2. Parses the Google-style docstring to extract parameter descriptions.
3. Generates JSON Schema for the serve layer (MCP, OpenAI, etc.).
4. Creates a synchronous wrapper from the async implementation.
5. Stores ``ActionMeta`` on the method for later introspection.
"""

from __future__ import annotations

import functools
import inspect
import re
import types
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from docstring_parser import parse as parse_docstring

from toolsconnector.runtime._sync import run_sync
from toolsconnector.spec.action import AccessKind, ParameterSpec
from toolsconnector.spec.pagination import PaginationSpec

# Union origins to unwrap: ``typing.Union`` (``Optional[X]`` / ``Union[...]``)
# and, on 3.10+, ``types.UnionType`` (PEP 604 ``X | None``). Filter out a
# missing ``UnionType`` on 3.9 so a non-union ``get_origin`` of ``None`` never
# matches a plain type.
_UNION_ORIGINS = tuple(o for o in (Union, getattr(types, "UnionType", None)) if o is not None)


@dataclass(frozen=True)
class ActionMeta:
    """Metadata for a single connector action.

    Attached to the method object as ``__action_meta__`` by the
    ``@action`` decorator.  Used by the serve layer, codegen, and
    documentation generators.

    Attributes:
        name: Method name (e.g., ``'list_emails'``).
        description: Human-readable one-line description.
        parameters: Ordered list of parameter metadata.
        input_schema: JSON Schema for action input (dict).
        output_schema: JSON Schema for action output (dict).
        return_type_name: String representation of the return type.
        requires_scope: OAuth scope name needed for this action.
        dangerous: Whether the action has destructive side effects.
        idempotent: Whether the action is safe to retry.
        pagination: Pagination configuration, if any.
        tags: Categorisation tags.
        rate_limit_weight: Rate-limit token cost for this action.
        deprecated: Whether the action is deprecated (kept callable for
            compatibility but no longer recommended / supported upstream).
        deprecation_message: Guidance surfaced with the deprecation —
            what to use instead, and why it was deprecated.
        long_description: The docstring prose beneath the ``@action`` title
            (summary + body, excluding the ``Args:``/``Returns:`` sections).
            This is the real usage contract — query syntax, examples, value
            formats, PUT-vs-PATCH semantics — that would otherwise be dropped
            before it ever reaches an LLM caller. Empty when there is no
            docstring prose.
    """

    name: str
    description: str
    long_description: str = ""
    parameters: list[ParameterSpec] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    return_type_name: str = "Any"
    requires_scope: Optional[str] = None
    dangerous: bool = False
    access: Optional[AccessKind] = None
    idempotent: bool = False
    pagination: Optional[PaginationSpec] = None
    tags: list[str] = field(default_factory=list)
    rate_limit_weight: int = 1
    deprecated: bool = False
    deprecation_message: Optional[str] = None


def _python_type_to_json_type(annotation: Any) -> str:
    """Map a Python type annotation to a JSON Schema type string."""
    origin = get_origin(annotation)
    if annotation is str:
        return "string"
    if annotation is bytes:
        # Binary inputs travel as base64 strings over JSON transport.
        return "string"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    if origin is list or annotation is list:
        return "array"
    if origin is dict or annotation is dict:
        return "object"
    return "string"


def _array_item_schema(annotation: Any) -> Optional[dict[str, Any]]:
    """Return the JSON Schema for a ``list[X]`` annotation's items, or None.

    Lets an array param advertise its element type (e.g. ``list[str]`` ->
    ``{"items": {"type": "string"}}``) instead of an untyped array, so MCP /
    OpenAI clients (and downstream arg coercion) know what the elements are.
    Bare ``list`` (no parameter) yields ``None``.
    """
    item_args = get_args(annotation)
    if not item_args:
        return None
    return {"type": _python_type_to_json_type(item_args[0])}


def _build_parameter_specs(
    func: Callable[..., Any],
) -> list[ParameterSpec]:
    """Extract parameter specs from a function's signature and docstring."""
    sig = inspect.signature(func)
    hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
    doc = parse_docstring(func.__doc__ or "")

    # Build a map of param name → docstring description
    doc_params: dict[str, str] = {}
    for dp in doc.params:
        doc_params[dp.arg_name] = dp.description or ""

    params: list[ParameterSpec] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue

        annotation = hints.get(name, Any)
        is_required = param.default is inspect.Parameter.empty
        default_val = None if is_required else param.default

        # Detect Optional/None unions and genuine multi-type unions. Use
        # ``get_origin``/``get_args`` so both ``typing.Union`` (``Optional[X]``)
        # and PEP 604 ``X | None`` (``types.UnionType``) are unwrapped -- the
        # old ``__origin__ is type(Optional[str])`` predicate never matched, so
        # every ``Optional[list[...]]`` fell through to the "string" default.
        nullable = False
        inner_type = annotation
        type_options: Optional[list[str]] = None
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin in _UNION_ORIGINS:
            nullable = type(None) in args
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                # Optional[X] / Union[X, None] -> the single underlying type.
                inner_type = non_none[0]
            elif len(non_none) >= 2:
                # Multi-type union (e.g. Union[str, list[str]]): collect the
                # distinct JSON Schema types so the schema can render an
                # ``anyOf``. Unions that collapse to one JSON type (e.g.
                # Union[bytes, str] -> "string") keep a single type.
                distinct: list[str] = []
                for a in non_none:
                    jt = _python_type_to_json_type(a)
                    if jt not in distinct:
                        distinct.append(jt)
                inner_type = non_none[0]
                if len(distinct) > 1:
                    type_options = distinct

        json_type = _python_type_to_json_type(inner_type)
        # Advertise element type for a single-type array param (e.g.
        # ``Optional[list[str]]`` -> array with ``items: {type: string}``).
        item_schema = (
            _array_item_schema(inner_type)
            if type_options is None and json_type == "array"
            else None
        )

        ps = ParameterSpec(
            name=name,
            type=json_type,
            description=doc_params.get(name, ""),
            required=is_required,
            default=default_val,
            nullable=nullable,
            type_options=type_options,
            items=item_schema,
        )
        params.append(ps)

    return params


def _build_input_schema(
    func: Callable[..., Any],
    param_specs: Sequence[ParameterSpec],
) -> dict[str, Any]:
    """Build a JSON Schema dict for the action's input parameters."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for ps in param_specs:
        # Multi-type union params render as ``anyOf`` so the schema (and
        # downstream MCP/OpenAI tool definitions) advertise every accepted
        # shape instead of collapsing to a single type. The lightweight
        # arg validator treats an ``anyOf`` (no top-level ``type``) as
        # permissive, so both forms pass validation.
        if ps.type_options:
            prop: dict[str, Any] = {"anyOf": [{"type": t} for t in ps.type_options]}
        else:
            prop = {"type": ps.type}
        if ps.description:
            prop["description"] = ps.description
        if ps.default is not None:
            prop["default"] = ps.default
        if ps.nullable:
            prop["nullable"] = True
        if ps.enum is not None:
            prop["enum"] = ps.enum
        if ps.format is not None:
            prop["format"] = ps.format
        if ps.items is not None:
            prop["items"] = ps.items

        properties[ps.name] = prop
        if ps.required:
            required.append(ps.name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


# A docstring with no summary line — one that starts directly with a section
# header like ``Args:`` — makes ``docstring_parser`` mis-detect the style and
# push the header (and raw parameter lines) into short/long_description. Detect
# a bare section header so we don't publish that leaked block as "prose".
_SECTION_HEADER_RE = re.compile(
    r"^(args|arguments|parameters|returns?|yields?|raises?|attributes?|notes?|"
    r"warnings?|examples?)\s*:?\s*$",
    re.IGNORECASE,
)


def _normalize_title(text: str) -> str:
    """Casefold and strip trailing sentence punctuation for equality checks."""
    return text.strip().rstrip(".!").strip().casefold()


def _extract_docstring_prose(func: Callable[..., Any], title: str = "") -> str:
    """Return a function's docstring summary + body (the prose above ``Args:``).

    The ``@action`` title is a one-liner; the docstring beneath it is where the
    real usage contract lives (query syntax, examples, value formats, PUT-vs-
    PATCH semantics, "use X instead" pointers). ``docstring_parser`` already
    splits that prose off from the ``Args:``/``Returns:`` sections — this
    recombines the summary and long body (the ``Args:`` block keeps flowing to
    parameter descriptions as before). Returns ``""`` when there is no prose.

    Two guards keep the published prose clean:

    * **Args-first docstrings** (no real summary) make ``docstring_parser``
      leak the parameter block into the summary/body — a bare section header in
      ``short_description`` signals that, so we return ``""``.
    * **Title-restating summaries** are dropped: when the summary merely repeats
      ``title`` (already published as the headline), it is omitted so the same
      sentence is never emitted twice.
    """
    doc = parse_docstring(func.__doc__ or "")
    short = (doc.short_description or "").strip()
    long_body = (doc.long_description or "").strip()

    # Mis-detected Args-first docstring — nothing publishable here.
    if short and _SECTION_HEADER_RE.match(short):
        return ""

    parts: list[str] = []
    if short and _normalize_title(short) != _normalize_title(title):
        parts.append(short)
    if long_body:
        parts.append(long_body)
    return "\n\n".join(parts)


def action(
    description: str,
    *,
    requires_scope: Optional[str] = None,
    dangerous: bool = False,
    access: Optional[AccessKind] = None,
    idempotent: bool = False,
    pagination: Optional[PaginationSpec] = None,
    tags: Optional[list[str]] = None,
    rate_limit_weight: int = 1,
    deprecated: bool = False,
    deprecation_message: Optional[str] = None,
) -> Callable[..., Any]:
    """Decorator that marks a method as a connector action.

    Args:
        description: Human-readable description of what this action does.
        requires_scope: OAuth scope name required for this action.
        dangerous: Whether this action has destructive side effects.
        access: Positive read/write classification — ``"read"`` | ``"write"`` |
            ``"destructive"``. Defaults to ``"destructive"`` when ``dangerous``
            is set (the two always agree); otherwise declare ``"read"`` or
            ``"write"`` explicitly. Tier-1 (live) connectors classify every
            action; a read-only consumer treats ``None`` as "not provably read".
        idempotent: Whether this action is safe to retry.
        pagination: Pagination configuration for list actions.
        tags: Categorization tags.
        rate_limit_weight: How many rate-limit tokens this action costs.
        deprecated: Mark the action deprecated — it stays callable for
            compatibility, but the flag is carried into the spec, docs,
            and serve layer.
        deprecation_message: What to use instead (and why), surfaced
            wherever the spec is rendered.

    Returns:
        Decorated method with ``__action_meta__`` attached.

    Example::

        class Gmail(BaseConnector):
            @action("List emails matching a query")
            async def list_emails(self, query: str = "is:unread") -> PaginatedList[Email]:
                ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Ensure the function is async
        if not inspect.iscoroutinefunction(func):
            raise TypeError(
                f"@action methods must be async. "
                f"Change '{func.__name__}' to 'async def {func.__name__}(...)'"
            )

        # Extract metadata
        param_specs = _build_parameter_specs(func)
        input_schema = _build_input_schema(func, param_specs)

        # Get return type name
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
        return_type = hints.get("return", Any)
        return_type_name = getattr(return_type, "__name__", str(return_type))

        # A dangerous action is always destructive; keep the two in agreement
        # without requiring every dangerous action to restate access.
        resolved_access: Optional[AccessKind] = access or ("destructive" if dangerous else None)

        # Build ActionMeta
        meta = ActionMeta(
            name=func.__name__,
            description=description,
            long_description=_extract_docstring_prose(func, description),
            parameters=param_specs,
            input_schema=input_schema,
            output_schema={},  # Populated when return type has model_json_schema
            return_type_name=return_type_name,
            requires_scope=requires_scope,
            dangerous=dangerous,
            access=resolved_access,
            idempotent=idempotent,
            pagination=pagination,
            tags=tags or [],
            rate_limit_weight=rate_limit_weight,
            deprecated=deprecated,
            deprecation_message=deprecation_message,
        )

        # Try to get output schema from return type
        if hasattr(return_type, "model_json_schema"):
            try:
                meta = ActionMeta(
                    **{
                        **{
                            f.name: getattr(meta, f.name)
                            for f in meta.__dataclass_fields__.values()
                        },
                        "output_schema": return_type.model_json_schema(),
                    }
                )
            except Exception:
                pass  # Some generic types may fail

        # Attach metadata to the async function
        func.__action_meta__ = meta  # type: ignore[attr-defined]

        # Create sync wrapper
        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            return run_sync(func(self, *args, **kwargs))

        sync_wrapper.__action_meta__ = meta  # type: ignore[attr-defined]
        sync_wrapper.__is_sync_wrapper__ = True  # type: ignore[attr-defined]

        # Store both versions on the function
        func.__sync_wrapper__ = sync_wrapper  # type: ignore[attr-defined]

        return func

    return decorator


def get_actions(cls: type) -> dict[str, ActionMeta]:
    """Extract all action metadata from a connector class.

    Args:
        cls: The connector class to inspect.

    Returns:
        Dict mapping action name to ActionMeta.
    """
    actions: dict[str, ActionMeta] = {}
    for name in dir(cls):
        method = getattr(cls, name, None)
        if method is not None and hasattr(method, "__action_meta__"):
            meta: ActionMeta = method.__action_meta__
            actions[meta.name] = meta
    return actions
