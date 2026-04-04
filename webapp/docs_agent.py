"""ToolsConnector Documentation Agent.

Interactive terminal assistant that answers developer questions
about ToolsConnector using natural language.

Usage:
    export OPENROUTER_API_KEY=sk-or-v1-...
    python webapp/docs_agent.py

Or without API key (uses offline knowledge base):
    python webapp/docs_agent.py --offline
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — ensure we can import from the project src/
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import httpx

# ---------------------------------------------------------------------------
# Rich terminal UI (graceful fallback to plain text)
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ---------------------------------------------------------------------------
# OpenRouter configuration
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free-tier models, tried in order
MODELS = [
    "qwen/qwen3-235b-a22b:free",
    "google/gemma-3-27b-it:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-4-maverick:free",
]

# ---------------------------------------------------------------------------
# Dynamic project introspection
# ---------------------------------------------------------------------------

def _build_connector_summary() -> tuple[str, str, int, int]:
    """Import live project data and return (connector_details, category_summary, n_connectors, n_actions).

    This reads from the actual installed package so the documentation agent
    is always in sync with the codebase.
    """
    from toolsconnector.serve import list_connectors, get_connector_class

    connector_lines: list[str] = []
    total_actions = 0
    categories: dict[str, list[str]] = {}

    for name in list_connectors():
        try:
            cls = get_connector_class(name)
            spec = cls.get_spec()
            n = len(spec.actions)
            total_actions += n
            cat = spec.category.value
            categories.setdefault(cat, []).append(name)
            actions_csv = ", ".join(sorted(spec.actions.keys()))
            connector_lines.append(
                f"- **{name}** ({spec.display_name}): category={cat}, "
                f"{n} actions: {actions_csv}"
            )
        except Exception as exc:
            connector_lines.append(f"- **{name}**: failed to load ({exc})")

    cat_summary = "\n".join(
        f"  {cat}: {', '.join(sorted(names))}"
        for cat, names in sorted(categories.items())
    )

    return (
        "\n".join(connector_lines),
        cat_summary,
        len(list_connectors()),
        total_actions,
    )


def build_system_prompt() -> str:
    """Build system prompt with live project context."""

    connector_details, cat_summary, n_connectors, n_actions = _build_connector_summary()

    return textwrap.dedent(f"""\
    You are the **ToolsConnector Documentation Assistant** — a helpful AI that
    answers developer questions about the ToolsConnector open-source project.

    Answer accurately and concisely. Include code examples when they clarify.
    If you genuinely don't know, say so.

    -----------------------------------------------------------------------
    ## What is ToolsConnector?
    ToolsConnector is a Foundation-grade Python library (Apache 2.0) that
    standardizes external API tool connections for **both** traditional Python
    applications (Django/Flask cron jobs, scripts) **and** AI agents
    (LangChain, Autogen, OpenAI function calling, Claude tool use).

    It is a *primitive*, not a platform — like Docker standardized containers,
    ToolsConnector standardizes tool integration.

    ## Installation
    ```bash
    pip install toolsconnector              # core
    pip install toolsconnector[gmail,slack]  # with specific connectors
    pip install toolsconnector[mcp]         # with MCP server support
    pip install toolsconnector[all]         # everything
    ```

    ## Core Concept: ToolKit
    Everything flows through ToolKit — one object for schema generation,
    execution, and serving:

    ```python
    from toolsconnector.serve import ToolKit

    kit = ToolKit(
        ["gmail", "slack", "github"],
        credentials={{"gmail": "token", "slack": "token", "github": "token"}},
        exclude_dangerous=True,
    )

    # --- Schema generation (pick your AI framework) ---
    tools = kit.to_openai_tools()       # OpenAI function calling
    tools = kit.to_anthropic_tools()    # Anthropic Claude tool use
    tools = kit.to_gemini_tools()       # Google Gemini

    # --- Execution ---
    result = kit.execute("gmail_list_emails", {{"query": "is:unread"}})
    result = await kit.aexecute("gmail_list_emails", {{"query": "is:unread"}})

    # --- Serving ---
    kit.serve_mcp()                     # MCP server for Claude Desktop / Cursor
    app = kit.create_rest_app()         # REST API server
    ```

    ## Multi-Tenant (SaaS)
    ```python
    from toolsconnector.serve import ToolKitFactory

    factory = ToolKitFactory(["gmail", "slack"], exclude_dangerous=True)
    user_kit = factory.for_tenant("user-123", credentials={{...}})
    ```

    ## Statistics
    - {n_connectors} connectors, {n_actions} total actions
    - Python 3.9+, Pydantic V2, httpx
    - 1,090+ tests passing

    ## Categories
    {cat_summary}

    ## All Connectors (live from codebase)
    {connector_details}

    ## Credential Management
    BYOK (Bring Your Own Key). Three approaches:
    1. Direct: `ToolKit(credentials={{"gmail": "token"}})`
    2. Environment: `export TC_GMAIL_CREDENTIALS=token`
    3. KeyStore: InMemoryKeyStore, EnvironmentKeyStore,
       LocalFileKeyStore (with Fernet encryption)

    ## Resilience Features
    - Circuit breaker per connector (opens after 5 consecutive failures)
    - Pre-validation of arguments against JSON Schema
    - Timeout budgets with deadline-aware retries
    - Auto token refresh on OAuth expiry
    - Graceful degradation (one connector fails, others continue)
    - Dry-run mode for dangerous actions

    ## CLI
    ```bash
    tc list                               # list all connectors
    tc gmail actions                      # show connector actions
    tc gmail list_emails --query "is:unread"  # execute an action
    tc serve mcp gmail slack              # start MCP server
    tc serve rest gmail slack --port 8000  # start REST server
    ```

    ## MCP Server Setup (Claude Desktop / Cursor)
    ```json
    {{
      "mcpServers": {{
        "toolsconnector": {{
          "command": "tc",
          "args": ["serve", "mcp", "gmail", "slack", "github"]
        }}
      }}
    }}
    ```
    Or programmatically:
    ```python
    kit = ToolKit(["gmail", "slack"], credentials={{...}})
    kit.serve_mcp()  # starts stdio-based MCP server
    ```

    ## OpenAI Integration Example
    ```python
    import openai
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gmail"], credentials={{"gmail": token}})
    tools = kit.to_openai_tools()

    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{{"role": "user", "content": "List my unread emails"}}],
        tools=tools,
    )

    # Execute tool calls from the response
    for call in response.choices[0].message.tool_calls:
        result = kit.execute(call.function.name,
                             json.loads(call.function.arguments))
    ```

    ## Anthropic Integration Example
    ```python
    import anthropic
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gmail"], credentials={{"gmail": token}})
    tools = kit.to_anthropic_tools()

    response = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        messages=[{{"role": "user", "content": "List my unread emails"}}],
        tools=tools,
    )
    ```

    ## How to Add a New Connector
    1. Create `src/toolsconnector/connectors/mytool/` with `__init__.py`
    2. Write `types.py` with Pydantic models (use `ConfigDict(frozen=True)`)
    3. Write `connector.py` subclassing `BaseConnector`
       - Decorate methods with `@action`
       - All action methods must be `async def`
    4. Register in `src/toolsconnector/serve/_discovery.py`
    5. Add tests in `tests/connectors/test_mytool.py`

    ## Architecture Decisions
    - Raw httpx for most connectors (no SDK wrapping tax)
    - SDKs only for Google and AWS (complex auth protocols)
    - No auth implementation in the library — BYOK only
    - Protocol adapters: REST, GraphQL, SOAP, gRPC, WebSocket, DB, MQ
    - PaginatedList for all list actions (consistent iteration)
    - @action decorator drives spec generation, schema, and CLI

    ## Error Handling
    All errors inherit from `ToolsConnectorError`:
    - `ConnectorNotConfiguredError` — unknown connector name
    - `ConnectorInitError` — missing dependencies
    - `AuthenticationError` — bad or expired credentials
    - `RateLimitError` — API rate limit hit (includes retry_after)
    - `ValidationError` — bad input parameters
    - `ExecutionError` — action failed at runtime
    """)


# ---------------------------------------------------------------------------
# Offline knowledge (subset for when no API key is set)
# ---------------------------------------------------------------------------

_OFFLINE_ANSWERS: dict[str, str] = {
    "install": textwrap.dedent("""\
        pip install toolsconnector              # core only
        pip install toolsconnector[gmail,slack]  # specific connectors
        pip install toolsconnector[mcp]         # MCP server support
        pip install toolsconnector[all]         # everything
    """),
    "quickstart": textwrap.dedent("""\
        from toolsconnector.serve import ToolKit

        kit = ToolKit(["gmail", "slack"], credentials={...})
        tools = kit.to_openai_tools()
        result = kit.execute("gmail_list_emails", {"query": "is:unread"})
    """),
    "mcp": textwrap.dedent("""\
        # CLI:
        tc serve mcp gmail slack

        # Python:
        kit = ToolKit(["gmail", "slack"], credentials={...})
        kit.serve_mcp()

        # Claude Desktop config:
        {
          "mcpServers": {
            "toolsconnector": {
              "command": "tc",
              "args": ["serve", "mcp", "gmail", "slack"]
            }
          }
        }
    """),
}


def _offline_search(query: str) -> str | None:
    """Try to match an offline answer to a query."""
    q = query.lower()
    for key, answer in _OFFLINE_ANSWERS.items():
        if key in q:
            return answer
    return None


# ---------------------------------------------------------------------------
# LLM communication
# ---------------------------------------------------------------------------

def chat_with_llm(messages: list[dict], model: str) -> str:
    """Call OpenRouter API with automatic model fallback.

    Tries ``model`` first, then falls back through MODELS list on failure.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/toolsconnector",
        "X-OpenRouter-Title": "ToolsConnector Docs Agent",
    }

    models_to_try = [model] + [m for m in MODELS if m != model]

    last_error = ""
    for m in models_to_try:
        payload = {
            "model": m,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3,
        }

        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(
                    OPENROUTER_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Some models return error inside the JSON body
                if "error" in data:
                    last_error = data["error"].get("message", str(data["error"]))
                    continue

                content = data["choices"][0]["message"]["content"]
                if not content:
                    last_error = "Empty response from model"
                    continue

                return content

        except httpx.HTTPStatusError as exc:
            last_error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            continue
        except httpx.RequestError as exc:
            last_error = f"Request error: {exc}"
            continue
        except (KeyError, IndexError) as exc:
            last_error = f"Unexpected response format: {exc}"
            continue

    return f"All models failed. Last error: {last_error}"


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_welcome() -> None:
    """Print the welcome banner."""
    welcome = textwrap.dedent("""\
        ToolsConnector Documentation Agent

        Ask me anything about ToolsConnector:
          - How to install and get started
          - How to use with OpenAI, Anthropic, or Claude Desktop
          - How to add a new connector
          - What connectors are available
          - How credentials and auth work
          - How resilience features work
          - Architecture decisions

        Commands:
          quit / exit / q   Stop the agent
          model <name>      Switch LLM model
          connectors        List all connectors (offline)
          help              Show this message again
    """)

    if HAS_RICH:
        console.print(
            Panel(
                welcome.strip(),
                title="[bold]ToolsConnector Assistant[/bold]",
                border_style="blue",
                padding=(1, 2),
            )
        )
    else:
        print(welcome)


def _print_response(text: str) -> None:
    """Render an assistant response."""
    if HAS_RICH:
        console.print()
        console.print(Markdown(text))
    else:
        print(f"\nAssistant: {text}")


def _print_info(text: str) -> None:
    """Print an informational message."""
    if HAS_RICH:
        console.print(f"[dim]{text}[/dim]")
    else:
        print(text)


def _print_warning(text: str) -> None:
    """Print a warning message."""
    if HAS_RICH:
        console.print(f"[yellow]{text}[/yellow]")
    else:
        print(f"WARNING: {text}")


def _print_connector_table() -> None:
    """Print a table of all connectors (works offline)."""
    from toolsconnector.serve import list_connectors, get_connector_class

    if HAS_RICH:
        table = Table(title="Available Connectors", border_style="blue")
        table.add_column("Name", style="bold cyan")
        table.add_column("Display Name")
        table.add_column("Category", style="green")
        table.add_column("Actions", justify="right", style="magenta")

        for name in list_connectors():
            try:
                cls = get_connector_class(name)
                spec = cls.get_spec()
                table.add_row(
                    name,
                    spec.display_name,
                    spec.category.value,
                    str(len(spec.actions)),
                )
            except Exception:
                table.add_row(name, "?", "?", "?")

        console.print(table)
    else:
        names = list_connectors()
        print(f"\nAvailable connectors ({len(names)}):")
        for name in names:
            try:
                cls = get_connector_class(name)
                spec = cls.get_spec()
                print(f"  {name:16s} {spec.display_name:20s} "
                      f"{spec.category.value:20s} {len(spec.actions)} actions")
            except Exception:
                print(f"  {name:16s} (failed to load)")


def _get_input(prompt_text: str) -> str:
    """Read a line of user input."""
    if HAS_RICH:
        return console.input(prompt_text)
    return input(prompt_text)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the interactive documentation agent."""

    _print_welcome()

    # Check for API key
    offline_mode = "--offline" in sys.argv or not OPENROUTER_API_KEY
    if offline_mode and "--offline" not in sys.argv:
        _print_warning(
            "No OPENROUTER_API_KEY found. Running in offline mode.\n"
            "Set it with: export OPENROUTER_API_KEY=sk-or-v1-...\n"
            "Get a free key at: https://openrouter.ai/keys\n"
        )

    # Build system prompt from live project data
    _print_info("Loading project context...")
    try:
        system_prompt = build_system_prompt()
        _print_info("Project context loaded successfully.")
    except Exception as exc:
        _print_warning(f"Could not load full project context: {exc}")
        _print_info("Falling back to basic knowledge.")
        system_prompt = (
            "You are the ToolsConnector Documentation Assistant. "
            "Answer questions about the ToolsConnector Python library. "
            "It standardizes API tool connections for Python apps and AI agents."
        )

    # Conversation history
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
    ]
    current_model = MODELS[0]

    while True:
        # Read input
        try:
            user_input = _get_input("\n[bold blue]You:[/bold blue] " if HAS_RICH else "\nYou: ")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # --- Built-in commands ---
        cmd = user_input.lower()

        if cmd in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        if cmd == "help":
            _print_welcome()
            continue

        if cmd == "connectors":
            _print_connector_table()
            continue

        if cmd.startswith("model "):
            new_model = user_input[6:].strip()
            if new_model:
                current_model = new_model
                _print_info(f"Switched to model: {current_model}")
            else:
                _print_info(f"Current model: {current_model}")
                _print_info(f"Available free models: {', '.join(MODELS)}")
            continue

        if cmd == "model":
            _print_info(f"Current model: {current_model}")
            _print_info(f"Available free models:")
            for m in MODELS:
                marker = " <-- active" if m == current_model else ""
                _print_info(f"  {m}{marker}")
            continue

        # --- Offline mode ---
        if offline_mode:
            offline_answer = _offline_search(user_input)
            if offline_answer:
                _print_response(offline_answer)
            elif cmd in ("list", "list connectors"):
                _print_connector_table()
            else:
                _print_info(
                    "(Offline mode -- set OPENROUTER_API_KEY for AI-powered answers)\n"
                    "Try: 'connectors', 'install', 'quickstart', or 'mcp'"
                )
            continue

        # --- LLM conversation ---
        messages.append({"role": "user", "content": user_input})

        # Call the LLM
        if HAS_RICH:
            with console.status("[bold green]Thinking...[/bold green]"):
                response = chat_with_llm(messages, current_model)
        else:
            print("Thinking...")
            response = chat_with_llm(messages, current_model)

        messages.append({"role": "assistant", "content": response})
        _print_response(response)

        # Keep conversation history manageable (system + last 20 turns)
        if len(messages) > 22:
            messages = [messages[0]] + messages[-20:]


if __name__ == "__main__":
    main()
