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
from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import (
    Any,
    Callable,
    Optional,
    get_type_hints,
)

from docstring_parser import parse as parse_docstring

from toolsconnector.runtime._sync import run_sync
from toolsconnector.spec.action import ParameterSpec
from toolsconnector.spec.pagination import PaginationSpec


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
    """

    name: str
    description: str
    parameters: list[ParameterSpec] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    return_type_name: str = "Any"
    requires_scope: Optional[str] = None
    dangerous: bool = False
    idempotent: bool = False
    pagination: Optional[PaginationSpec] = None
    tags: list[str] = field(default_factory=list)
    rate_limit_weight: int = 1


def _python_type_to_json_type(annotation: Any) -> str:
    """Map a Python type annotation to a JSON Schema type string."""
    origin = getattr(annotation, "__origin__", None)
    if annotation is str:
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

        # Detect Optional/None union
        nullable = False
        inner_type = annotation
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())
        if origin is type(Optional[str]):  # Union
            # Check if it's Optional (Union[X, None])
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1 and type(None) in args:
                nullable = True
                inner_type = non_none[0]

        json_type = _python_type_to_json_type(inner_type)

        ps = ParameterSpec(
            name=name,
            type=json_type,
            description=doc_params.get(name, ""),
            required=is_required,
            default=default_val,
            nullable=nullable,
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
        prop: dict[str, Any] = {"type": ps.type}
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


def action(
    description: str,
    *,
    requires_scope: Optional[str] = None,
    dangerous: bool = False,
    idempotent: bool = False,
    pagination: Optional[PaginationSpec] = None,
    tags: Optional[list[str]] = None,
    rate_limit_weight: int = 1,
) -> Callable[..., Any]:
    """Decorator that marks a method as a connector action.

    Args:
        description: Human-readable description of what this action does.
        requires_scope: OAuth scope name required for this action.
        dangerous: Whether this action has destructive side effects.
        idempotent: Whether this action is safe to retry.
        pagination: Pagination configuration for list actions.
        tags: Categorization tags.
        rate_limit_weight: How many rate-limit tokens this action costs.

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

        # Build ActionMeta
        meta = ActionMeta(
            name=func.__name__,
            description=description,
            parameters=param_specs,
            input_schema=input_schema,
            output_schema={},  # Populated when return type has model_json_schema
            return_type_name=return_type_name,
            requires_scope=requires_scope,
            dangerous=dangerous,
            idempotent=idempotent,
            pagination=pagination,
            tags=tags or [],
            rate_limit_weight=rate_limit_weight,
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
