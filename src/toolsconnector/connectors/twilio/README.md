# Twilio

> Communication APIs for SMS, voice, and video

| | |
|---|---|
| **Company** | Twilio Inc. |
| **Category** | Communication |
| **Protocol** | REST |
| **Website** | [twilio.com](https://twilio.com) |
| **API Docs** | [www.twilio.com](https://www.twilio.com/docs/usage/api) |
| **Auth** | Basic Auth (Account SID + Auth Token) |
| **Rate Limit** | Varies by service |
| **Pricing** | Pay-per-use (SMS from $0.0079/msg) |

---

## Overview

The Twilio API provides SMS messaging, voice calls, and communication services. Send and receive text messages, make and manage phone calls, verify phone numbers, and build multi-channel communication workflows.

## Use Cases

- SMS notifications
- Two-factor authentication
- Voice call automation
- Phone number verification
- WhatsApp messaging

## Installation

```bash
pip install "toolsconnector[twilio]"
```

Set your credentials:

```bash
export TC_TWILIO_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["twilio"], credentials={"twilio": "your-token"})

# List SMS/MMS messages from your Twilio account
result = kit.execute("twilio_list_messages", {"to": "recipient@example.com", "from_": "your-from_"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["twilio"], credentials={"twilio": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["twilio"], credentials={"twilio": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Basic Auth (Account SID + Auth Token)

1. Create an account at [Twilio](https://twilio.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.twilio.com/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("twilio_list_messages", {})
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

- Rate limit is Varies by service — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_conversation`, `create_verify_service`, `delete_message`) cannot be undone — use with caution

## Related Connectors

- [Gmail](../gmail/) — Email automation
- [Slack](../slack/) — Team messaging
- [Discord](../discord/) — Community messaging
- [Teams](../teams/) — Microsoft collaboration

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
