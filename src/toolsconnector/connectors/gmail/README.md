# Gmail

> Read, send, and manage emails programmatically

| | |
|---|---|
| **Company** | Google |
| **Category** | Communication |
| **Protocol** | REST |
| **Base URL** | `https://gmail.googleapis.com/gmail/v1` |
| **Website** | [mail.google.com](https://mail.google.com) |
| **API Docs** | [developers.google.com](https://developers.google.com/workspace/gmail/api/reference/rest) |
| **Auth** | OAuth 2.0, Service Account |
| **Rate Limit** | 250 requests/second per user |
| **Pricing** | Free (Google Workspace required for some features) |

---

## Overview

The Gmail API lets you read, compose, send, and organize email messages and threads. Use it to build email automation, customer communication workflows, notification systems, and email analytics pipelines. Supports OAuth 2.0 for user-level access and Service Accounts for domain-wide access in Google Workspace.

## Use Cases

- Email automation and scheduling
- Customer support ticket creation from emails
- Email analytics and reporting
- Newsletter management
- Automated replies and forwarding rules
- Email migration between accounts
- Audit and compliance monitoring

## Installation

```bash
pip install "toolsconnector[gmail]"
```

Set your credentials:

```bash
export TC_GMAIL_CREDENTIALS=your-oauth-access-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gmail"], credentials={"gmail": "your-token"})

# List unread emails
result = kit.execute("gmail_list_emails", {"query": "is:unread", "limit": 5})
print(result)

# Send an email
result = kit.execute("gmail_send_email", {
    "to": "recipient@example.com",
    "subject": "Hello from ToolsConnector",
    "body": "<h1>Hello!</h1><p>Sent via Gmail connector.</p>"
})
```

### MCP Server

```python
kit = ToolKit(["gmail"], credentials={"gmail": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gmail"], credentials={"gmail": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0 (recommended for user accounts)

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project (or select existing)
3. Enable the **Gmail API** under APIs & Services
4. Create **OAuth 2.0 Client ID** credentials
5. Set authorized redirect URIs for your application
6. Use the obtained access token as your credential

### Service Account (for domain-wide access)

1. Create a service account in Google Cloud Console
2. Enable domain-wide delegation in Google Workspace Admin
3. Download the JSON key file
4. Use the access token obtained via the service account

### Scopes

| Scope | Access Level |
|---|---|
| `gmail.readonly` | Read emails, threads, labels |
| `gmail.send` | Send emails and drafts |
| `gmail.modify` | Full read/write access |
| `gmail.labels` | Manage labels only |

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError, NotFoundError

try:
    result = kit.execute("gmail_list_emails", {"query": "is:unread"})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
except NotFoundError as e:
    print(f"Email not found: {e.message}")
```

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- Run: python -m toolsconnector.codegen.generate_action_docs gmail -->
<!-- ACTIONS_END -->

## Tips

- Use Gmail search syntax in the `query` parameter: `from:boss@company.com has:attachment after:2024/01/01`
- For bulk operations, use `batch_modify` and `batch_delete` instead of individual calls
- Thread operations (`list_threads`, `get_thread`) group related messages together
- Use `list_history` with a `startHistoryId` for efficient incremental sync
- Labels are case-sensitive: `"INBOX"`, `"UNREAD"`, `"STARRED"`
- The `trash_email` action is reversible (use `untrash_email`), but `delete_email` is permanent

## Related Connectors

- [Google Drive](../gdrive/) — File storage and sharing
- [Google Calendar](../gcalendar/) — Event scheduling
- [Google Sheets](../gsheets/) — Spreadsheet data
- [Microsoft Outlook](../outlook/) — Alternative email connector
- [SendGrid](../sendgrid/) — Transactional email sending

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
