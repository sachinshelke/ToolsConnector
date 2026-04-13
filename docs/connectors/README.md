# All Connectors

ToolsConnector ships with 53 connectors organized into 17 categories, providing 1,137 total actions across communication, CRM, databases, DevOps, AI/ML, finance, and more.

## How Connectors Work

Every connector is a Python class that subclasses `BaseConnector` and exposes methods decorated with `@action`. Each action defines its parameters as a typed Pydantic model, includes a human-readable description, and declares whether the action is dangerous (mutating or side-effecting).

You interact with connectors through the `ToolKit` interface:

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gmail", "github"], credentials={
    "gmail": "ya29.your-token",
    "github": "ghp_your-token",
})

# Discover all available actions
tools = kit.list_tools()

# Execute an action
result = kit.execute("gmail_list_emails", {"query": "is:unread"})
```

## Connectors by Category

| Category | Connectors | Actions |
|---|---|---|
| [Communication](communication.md) | Gmail, Slack, Discord, Outlook, Teams, Twilio, Telegram | 200 |
| [Code Platforms](code-platforms.md) | GitHub, GitLab | 58 |
| [Project Management](project-management.md) | Jira, Asana, Linear, Trello | 110 |
| [CRM & Support](crm.md) | HubSpot, Salesforce, Zendesk, Freshdesk, Intercom | 95 |
| [Database](database.md) | Airtable, Firestore, MongoDB, Redis, Supabase | 93 |
| [DevOps & Cloud](devops.md) | Cloudflare, Datadog, Docker Hub, PagerDuty, Vercel | 91 |
| Productivity | Google Calendar, Docs, Sheets, Tasks, Calendly, Figma | 96 |
| [AI/ML](ai-ml.md) | OpenAI, Anthropic, Pinecone | 55 |
| [Finance & Payments](finance.md) | Stripe, Plaid | 57 |
| Knowledge | Notion, Confluence | 45 |
| Marketing | Mailchimp, SendGrid | 43 |
| [Storage](storage.md) | Google Drive, S3 | 42 |
| Security & Identity | Auth0, Okta | 48 |
| Message Queue | SQS, RabbitMQ | 37 |
| Analytics | Mixpanel, Segment | 28 |
| E-Commerce | Shopify | 27 |
| Custom | Webhook | 12 |

## Authentication

All connectors follow the BYOK (Bring Your Own Key) model. You provide API tokens, OAuth access tokens, or API keys directly. ToolsConnector never stores, manages, or exchanges credentials on your behalf.

See the [Credentials Guide](../guides/credentials.md) for details on authentication patterns for each connector.
