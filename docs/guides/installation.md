# Installation

ToolsConnector requires Python 3.9 or later.

## Basic Install

Install the core library with no connector-specific dependencies:

```bash
pip install toolsconnector
```

The core package includes the `ToolKit` interface, CLI, schema generation, and all connectors that communicate over plain HTTP (the majority). A few connectors require additional SDKs -- install them with extras.

## Installing Connector Extras

Some connectors depend on third-party SDKs. Install only the ones you need:

```bash
pip install "toolsconnector[gmail,slack,s3]"
```

Connectors that require extras:

| Extra | Dependencies |
|---|---|
| `gmail` | `google-api-python-client`, `google-auth`, `google-auth-oauthlib` |
| `gdrive` | `google-api-python-client`, `google-auth` |
| `gcalendar` | `google-api-python-client`, `google-auth` |
| `s3` | `boto3` |
| `sqs` | `boto3` |

All other connectors (Slack, GitHub, Jira, Stripe, etc.) use `httpx` from the core package and require no additional dependencies.

## Category Bundles

Install an entire category of connectors at once:

```bash
pip install "toolsconnector[communication]"   # Gmail, Slack, Discord, Telegram, Twilio
pip install "toolsconnector[project-mgmt]"     # Jira, Asana, Linear, Trello
pip install "toolsconnector[databases]"        # Supabase, MongoDB, Airtable, Firestore, Redis
pip install "toolsconnector[devops]"           # Datadog, PagerDuty, Vercel, Cloudflare, Docker Hub
pip install "toolsconnector[crm]"             # HubSpot, Salesforce, Zendesk, Freshdesk, Intercom
pip install "toolsconnector[ai]"              # OpenAI, Anthropic, Pinecone
pip install "toolsconnector[google]"          # Gmail, Google Drive, Google Calendar
pip install "toolsconnector[microsoft]"       # Outlook, Teams
```

## Protocol Extras

To use the MCP server or REST server, install the corresponding extras:

```bash
pip install "toolsconnector[mcp]"    # MCP server support (requires mcp>=1.0)
pip install "toolsconnector[rest]"   # REST server support (Starlette + Uvicorn)
```

## Virtual Environments

We recommend using a virtual environment to avoid dependency conflicts:

```bash
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\activate             # Windows

pip install "toolsconnector[gmail,slack,mcp]"
```

## Verify Installation

After installation, verify that the CLI is available and connectors are registered:

```bash
tc list
```

This prints a table of all 53 connectors with their category, action count, and whether they require extras.

You can also verify from Python:

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["slack"], credentials={"slack": "test"})
tools = kit.list_tools()
print(f"Registered {len(tools)} tools")
```

## Python Version Requirements

ToolsConnector supports Python 3.9 and later. It uses modern typing features (`list[str]` instead of `List[str]`) and requires `asyncio` for async operations. Python 3.11+ is recommended for best async performance.
