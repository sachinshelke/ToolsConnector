# All Connectors

ToolsConnector ships with 50 connectors organized into 17 categories, providing 395 total actions across communication, CRM, databases, DevOps, AI/ML, finance, and more.

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
| [Communication](communication.md) | Gmail, Slack, Discord, Outlook, Teams, Twilio, Telegram | 56 |
| [Code Platforms](code-platforms.md) | GitHub, GitLab | 18 |
| [Project Management](project-management.md) | Jira, Asana, Linear, Trello | 32 |
| [CRM & Support](crm.md) | HubSpot, Salesforce, Zendesk, Freshdesk, Intercom | 40 |
| [Database](database.md) | Supabase, MongoDB, Airtable, Firestore, Redis | 39 |
| [DevOps & Cloud](devops.md) | Datadog, PagerDuty, Vercel, Cloudflare, Docker Hub | 40 |
| [AI/ML](ai-ml.md) | OpenAI, Anthropic, Pinecone | 19 |
| [Finance & Payments](finance.md) | Stripe, Plaid | 16 |
| [Storage](storage.md) | Google Drive, S3 | 16 |
| Knowledge | Notion, Confluence | 16 |
| Marketing | SendGrid, Mailchimp | 16 |
| E-commerce | Shopify | 8 |
| Scheduling | Google Calendar, Calendly | 14 |
| Analytics | Mixpanel, Segment | 16 |
| Message Queue | SQS, RabbitMQ | 16 |
| Security & Identity | Auth0, Okta | 16 |
| Design | Figma | 8 |
| General | Webhook | 8 |

## Authentication

All connectors follow the BYOK (Bring Your Own Key) model. You provide API tokens, OAuth access tokens, or API keys directly. ToolsConnector never stores, manages, or exchanges credentials on your behalf.

See the [Credentials Guide](../guides/credentials.md) for details on authentication patterns for each connector.
