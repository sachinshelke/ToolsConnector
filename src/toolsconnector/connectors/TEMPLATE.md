# {Tool Name}

> {One-line description of what this tool does}

| | |
|---|---|
| **Company** | {Company name} |
| **Category** | {Category} |
| **Protocol** | {REST / GraphQL / etc.} |
| **Base URL** | `{API base URL}` |
| **Website** | [{domain}]({full URL}) |
| **API Docs** | [{docs domain}]({full docs URL}) |
| **Auth** | {OAuth 2.0 / API Key / Bearer Token / etc.} |
| **Rate Limit** | {rate description} |
| **Pricing** | {pricing description} |

---

## Overview

{2-3 sentences describing what this API does, what you can build with it,
and what authentication it supports.}

## Use Cases

- {Use case 1}
- {Use case 2}
- {Use case 3}
- {Use case 4}
- {Use case 5}

## Installation

```bash
pip install toolsconnector[{name}]
```

Set your credentials:

```bash
export TC_{NAME}_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["{name}"], credentials={"{name}": "your-token"})

# {Most common action description}
result = kit.execute("{name}_{first_action}", {
    "{param1}": "{value1}",
    "{param2}": "{value2}",
})
print(result)
```

### MCP Server

```python
kit = ToolKit(["{name}"], credentials={"{name}": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["{name}"], credentials={"{name}": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### {Primary Auth Method}

1. {Step 1}
2. {Step 2}
3. {Step 3}

[Get credentials →]({credentials URL})

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("{name}_{action}", {...})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
```

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- {Tip 1 — something developers often get wrong}
- {Tip 2 — a useful pattern or shortcut}
- {Tip 3 — performance or rate limit advice}

## Related Connectors

- [{Related 1}](../{name1}/) — {why related}
- [{Related 2}](../{name2}/) — {why related}

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
