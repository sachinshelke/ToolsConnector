# ToolsConnector

**One interface, every tool. Connect 50+ APIs to your Python app or AI agent in minutes.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Pydantic V2](https://img.shields.io/badge/pydantic-v2-e92063.svg)](https://docs.pydantic.dev/)

---

## The Problem

Every SaaS API has its own SDK, its own auth dance, its own pagination scheme, and its own error format. If you're building an AI agent, you also need to generate JSON Schema for function calling -- differently for OpenAI, Anthropic, and Gemini. You end up writing glue code instead of product code.

ToolsConnector gives you a single, typed Python interface to 50 connectors and 395 actions. It works identically whether you're building a Django app, an OpenAI agent, or an MCP server for Claude Desktop.

## Install

```bash
pip install toolsconnector
```

Install only the connectors you need:

```bash
pip install "toolsconnector[gmail,slack,github]"
```

Or install a full category:

```bash
pip install "toolsconnector[communication,databases,mcp]"
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["gmail", "slack"],
    credentials={"gmail": "ya29.access-token", "slack": "xoxb-bot-token"},
)

# List unread emails
result = kit.execute("gmail_list_emails", {"query": "is:unread", "max_results": 5})

# Send a Slack message
kit.execute("slack_send_message", {"channel": "#general", "text": "Deployed v2.1"})
```

That's it. Same `ToolKit`, same `.execute()`, every connector.

---

## Key Features

- **50 connectors, 395 actions** across 17 categories -- communication, databases, DevOps, CRM, AI/ML, and more
- **Dual-use design** -- works for traditional Python apps (Django, Flask, FastAPI) and AI agents (function calling, tool use) with zero code changes
- **One-line MCP server** -- expose any combination of connectors to Claude Desktop, Cursor, or any MCP client
- **Schema generation** -- produces OpenAI, Anthropic, and Gemini function-calling schemas from the same source of truth
- **Type-safe everywhere** -- Pydantic V2 models for all inputs and outputs, with full JSON Schema generation
- **Async-first, sync-friendly** -- every action has both `await kit.aexecute()` and `kit.execute()` paths
- **Circuit breakers** -- per-connector failure isolation so one dead API doesn't take down your agent
- **Timeout budgets** -- per-action and per-request deadlines with automatic retry on transient failures
- **Dry-run mode** -- validate destructive actions without executing them
- **BYOK auth** -- bring your own API keys and tokens; no OAuth server required in the library
- **Minimal dependencies** -- core requires only `pydantic`, `httpx`, and `docstring-parser`

---

## Workflows

### 1. Direct Python Usage

Use connectors directly in any Python application.

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["github"], credentials={"github": "ghp_your_token"})

# List open issues
issues = kit.execute("github_list_issues", {
    "owner": "myorg",
    "repo": "myproject",
    "state": "open",
})
```

### 2. MCP Server (One Line)

Expose connectors to Claude Desktop, Cursor, Windsurf, or any MCP client.

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["gmail", "gcalendar", "notion"],
    credentials={"gmail": "ya29.token", "gcalendar": "ya29.token", "notion": "ntn_key"},
)
kit.serve_mcp()  # stdio transport, ready for Claude Desktop
```

Or from the command line:

```bash
tc serve mcp gmail gcalendar notion --transport stdio
```

### 3. OpenAI Function Calling

Generate tool schemas and execute tool calls from OpenAI responses.

```python
from openai import OpenAI
from toolsconnector.serve import ToolKit

client = OpenAI()
kit = ToolKit(["gmail", "slack"], credentials={...})

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Summarize my unread emails"}],
    tools=kit.to_openai_tools(),
)

# Execute the tool call the model chose
tool_call = response.choices[0].message.tool_calls[0]
result = kit.execute(tool_call.function.name, tool_call.function.arguments)
```

### 4. Anthropic Tool Use

Works the same way with Claude's tool use API.

```python
import anthropic
from toolsconnector.serve import ToolKit

client = anthropic.Anthropic()
kit = ToolKit(["jira", "slack"], credentials={...})

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Create a bug ticket for the login issue"}],
    tools=kit.to_anthropic_tools(),
)

# Execute the tool call
for block in response.content:
    if block.type == "tool_use":
        result = kit.execute(block.name, block.input)
```

### 5. Google Gemini

Generate Gemini-compatible function declarations.

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gmail"], credentials={...})
declarations = kit.to_gemini_tools()
# Pass to google.generativeai as function_declarations
```

### 6. CLI Usage

Manage connectors and execute actions from the terminal.

```bash
# List all available connectors
tc list

# List actions for a specific connector
tc gmail actions

# Execute an action
tc gmail list_emails --query "is:unread" --max_results 5

# Export the connector spec
tc gmail spec --format json
```

### 7. REST API

Serve connectors as HTTP endpoints with Starlette/ASGI.

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["stripe", "hubspot"], credentials={...})
app = kit.create_rest_app(prefix="/api/v1")

# Run with uvicorn: uvicorn myapp:app --port 8000
# POST /api/v1/stripe/create_charge {"amount": 5000, "currency": "usd"}
```

---

## Supported Connectors

50 connectors across 17 categories.

### Communication (7)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Gmail | `gmail` | 8 |
| Slack | `slack` | 8 |
| Discord | `discord` | 8 |
| Microsoft Outlook | `outlook` | 8 |
| Microsoft Teams | `teams` | 8 |
| Twilio | `twilio` | 8 |
| Telegram | `telegram` | 8 |

### Project Management (4)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Jira | `jira` | 8 |
| Asana | `asana` | 8 |
| Linear | `linear` | 8 |
| Trello | `trello` | 8 |

### CRM and Support (5)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| HubSpot | `hubspot` | 8 |
| Salesforce | `salesforce` | 8 |
| Zendesk | `zendesk` | 8 |
| Freshdesk | `freshdesk` | 8 |
| Intercom | `intercom` | 8 |

### Code Platforms (2)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| GitHub | `github` | 10 |
| GitLab | `gitlab` | 8 |

### Knowledge (2)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Notion | `notion` | 8 |
| Confluence | `confluence` | 8 |

### Storage (2)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Google Drive | `gdrive` | 8 |
| AWS S3 | `s3` | 8 |

### Database (5)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Supabase | `supabase` | 8 |
| MongoDB Atlas | `mongodb` | 8 |
| Airtable | `airtable` | 8 |
| Firebase Firestore | `firestore` | 8 |
| Redis (Upstash) | `redis` | 8 |

### DevOps (5)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Datadog | `datadog` | 8 |
| PagerDuty | `pagerduty` | 8 |
| Vercel | `vercel` | 8 |
| Cloudflare | `cloudflare` | 8 |
| Docker Hub | `dockerhub` | 8 |

### Finance (2)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Stripe | `stripe` | 8 |
| Plaid | `plaid` | 8 |

### Marketing (2)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| SendGrid | `sendgrid` | 8 |
| Mailchimp | `mailchimp` | 8 |

### AI and ML (3)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| OpenAI | `openai` | 8 |
| Anthropic | `anthropic` | 3 |
| Pinecone | `pinecone` | 8 |

### Analytics (2)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Mixpanel | `mixpanel` | 8 |
| Segment | `segment` | 8 |

### Message Queue (2)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| AWS SQS | `sqs` | 8 |
| RabbitMQ | `rabbitmq` | 8 |

### Security (2)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Okta | `okta` | 8 |
| Auth0 | `auth0` | 8 |

### Productivity (3)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Google Calendar | `gcalendar` | 6 |
| Calendly | `calendly` | 8 |
| Figma | `figma` | 8 |

### E-commerce (1)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Shopify | `shopify` | 8 |

### Custom (1)

| Connector | Install Extra | Actions |
|-----------|---------------|---------|
| Webhook | `webhook` | 8 |

---

## Architecture

ToolsConnector is structured as four layers, each with a single responsibility:

```
+------------------------------------------------------------------+
|  Serve Layer       ToolKit, MCP, REST, CLI, Schema Generation    |
+------------------------------------------------------------------+
|  Runtime Engine    BaseConnector, @action, Middleware, Auth       |
+------------------------------------------------------------------+
|  Connectors        Gmail, Slack, GitHub, Stripe, ... (50)        |
+------------------------------------------------------------------+
|  Spec Types        Pydantic V2 models, JSON Schema, Contracts    |
+------------------------------------------------------------------+
```

**Spec** -- Pure Pydantic V2 models defining the language-agnostic connector contract. No implementation logic. These drive schema generation, MCP serving, documentation, and code generation.

**Runtime** -- The execution engine. `BaseConnector` is the abstract base class. The `@action` decorator parses type hints and docstrings to generate JSON Schema automatically. Middleware handles retry, rate limiting, auth refresh, and structured logging.

**Connectors** -- 50 implementations, each following the same pattern: subclass `BaseConnector`, set metadata, implement `@action` methods. Most use raw `httpx` for direct HTTP calls. Google and AWS connectors use official SDKs where protocol complexity justifies it.

**Serve** -- The `ToolKit` ties everything together. Configure once with a list of connectors and credentials, then serve as MCP, generate OpenAI/Anthropic/Gemini schemas, expose as REST, or call directly from Python.

### Adding a Connector

Every connector follows the same structure:

```python
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType

class MyService(BaseConnector):
    name = "myservice"
    display_name = "My Service"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://api.myservice.com/v1"

    @action(description="List all items", idempotent=True)
    async def list_items(self, limit: int = 20) -> list[dict]:
        """List items from the service.

        Args:
            limit: Maximum number of items to return.
        """
        resp = await self._request("GET", "/items", params={"limit": limit})
        return resp.json()["items"]
```

The `@action` decorator handles everything: it parses the type hints and docstring to generate JSON Schema, creates a sync wrapper, and registers the method for discovery by `ToolKit`.

---

## Contributing

1. Fork the repository
2. Create a connector under `src/toolsconnector/connectors/yourservice/`
3. Subclass `BaseConnector` and implement `@action` methods
4. Add types in a `types.py` module using Pydantic V2 models
5. Add the install extra to `pyproject.toml`
6. Write tests under `tests/connectors/yourservice/`
7. Submit a pull request

See the existing connectors (e.g., `src/toolsconnector/connectors/slack/`) for reference implementations.

## Requirements

- Python 3.9+
- Core dependencies: `pydantic>=2.0`, `httpx>=0.25`, `docstring-parser>=0.15`
- Connector-specific dependencies installed via extras (e.g., `gmail` extra installs `google-api-python-client`)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
