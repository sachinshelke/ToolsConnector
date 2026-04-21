"""Framework adapters for LangChain, CrewAI, and other agent frameworks.

Generates tools with execution built in -- the AI framework calls the tool
and gets a real result, no manual wiring needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolsconnector.serve.toolkit import ToolKit


def _make_sync_func(toolkit: ToolKit, tool_name: str, description: str) -> Any:
    """Return a sync callable with a clean ``**kwargs``-only signature.

    Using a factory prevents ``tool_name`` from appearing as a positional
    parameter when LangChain calls ``inspect.signature()`` to build its
    args schema.

    Args:
        toolkit: ToolKit instance that owns the connector.
        tool_name: Fully-qualified tool name.
        description: Human-readable description for the tool.

    Returns:
        A sync callable ``(**kwargs) -> str``.
    """

    def func(**kwargs: Any) -> str:
        return toolkit.execute(tool_name, kwargs)

    func.__name__ = tool_name
    func.__doc__ = description
    return func


def _make_async_func(toolkit: ToolKit, tool_name: str, description: str) -> Any:
    """Return an async callable with a clean ``**kwargs``-only signature.

    Using a factory prevents ``tool_name`` from appearing as a positional
    parameter when LangChain calls ``inspect.signature()`` to build its
    args schema.

    Args:
        toolkit: ToolKit instance that owns the connector.
        tool_name: Fully-qualified tool name.
        description: Human-readable description for the tool.

    Returns:
        An async callable ``(**kwargs) -> str``.
    """

    async def afunc(**kwargs: Any) -> str:
        return await toolkit.aexecute(tool_name, kwargs)

    afunc.__name__ = tool_name
    afunc.__doc__ = description
    return afunc


def to_langchain_tools(toolkit: ToolKit) -> list:
    """Generate LangChain StructuredTool objects with built-in execution.

    Each tool wraps a ToolKit action so LangChain agents can call
    connector actions directly.

    Requires langchain-core: pip install langchain-core

    Args:
        toolkit: Configured ToolKit instance.

    Returns:
        List of LangChain StructuredTool objects.

    Raises:
        ImportError: If langchain-core is not installed.
    """
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        raise ImportError(
            "LangChain adapter requires 'langchain-core'. Install with: pip install langchain-core"
        )

    tools: list = []
    for entry_dict in toolkit.list_tools():
        tool_name: str = entry_dict["name"]
        description: str = entry_dict["description"]

        # Use module-level factory functions so 'tool_name' is never visible
        # as a positional parameter to inspect.signature() / schema generators.
        tool = StructuredTool.from_function(
            func=_make_sync_func(toolkit, tool_name, description),
            name=tool_name,
            description=description,
            coroutine=_make_async_func(toolkit, tool_name, description),
        )
        tools.append(tool)

    return tools


def to_crewai_tools(toolkit: ToolKit) -> list:
    """Generate CrewAI-compatible tools.

    CrewAI uses a similar tool interface to LangChain.
    Falls back to the LangChain adapter.

    Args:
        toolkit: Configured ToolKit instance.

    Returns:
        List of CrewAI-compatible tool objects.
    """
    # CrewAI accepts LangChain tools
    return to_langchain_tools(toolkit)
