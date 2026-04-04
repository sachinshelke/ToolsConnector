"""Framework adapters for LangChain, CrewAI, and other agent frameworks.

Generates tools with execution built in -- the AI framework calls the tool
and gets a real result, no manual wiring needed.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from toolsconnector.serve.toolkit import ToolKit


def to_langchain_tools(toolkit: "ToolKit") -> list:
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
            "LangChain adapter requires 'langchain-core'. "
            "Install with: pip install langchain-core"
        )

    tools: list = []
    for entry_dict in toolkit.list_tools():
        tool_name: str = entry_dict["name"]
        description: str = entry_dict["description"]
        input_schema: dict[str, Any] = entry_dict.get("input_schema", {})

        # Build the args_schema as a dict for StructuredTool
        # StructuredTool accepts a function + description

        def _make_func(tn: str = tool_name) -> Any:
            def func(**kwargs: Any) -> str:
                return toolkit.execute(tn, kwargs)
            func.__name__ = tn
            func.__doc__ = description
            return func

        def _make_afunc(tn: str = tool_name) -> Any:
            async def afunc(**kwargs: Any) -> str:
                return await toolkit.aexecute(tn, kwargs)
            afunc.__name__ = tn
            afunc.__doc__ = description
            return afunc

        tool = StructuredTool.from_function(
            func=_make_func(),
            name=tool_name,
            description=description,
            coroutine=_make_afunc(),
        )
        tools.append(tool)

    return tools


def to_crewai_tools(toolkit: "ToolKit") -> list:
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
