# All Connectors

ToolsConnector ships with 73 connectors organized into 20 categories, providing 1,519 total actions across communication, CRM, databases, DevOps, AI/ML, finance, productivity, and more.

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
| [Communication](communication.md) | Gmail, Slack, Discord, Outlook, Teams, Twilio, Telegram | 228 |
| [AI/ML](ai-ml.md) | Anthropic, OpenAI, Pinecone, Hugging Face, Gemini, Cohere, Mistral, Groq | 172 |
| [DevOps & Cloud](devops.md) | Cloudflare, CloudWatch, Datadog, Docker Hub, ECR, PagerDuty, Vercel | 123 |
| [Database](database.md) | Airtable, Firestore, MongoDB, RDS, Redis, Supabase | 118 |
| [Project Management](project-management.md) | Asana, Jira, Linear, Trello | 110 |
| [Productivity](productivity.md) | Google Calendar, Docs, Sheets, Tasks, Calendly, Figma | 96 |
| [CRM & Support](crm.md) | Freshdesk, HubSpot, Intercom, Salesforce, Zendesk | 95 |
| Security & Identity | ACM, Auth0, IAM, Okta, Secrets Manager | 90 |
| Compute | EC2, ECS, Lambda | 70 |
| [Code Platforms](code-platforms.md) | GitHub, GitLab | 58 |
| [Finance & Payments](finance.md) | Plaid, Stripe | 57 |
| [Knowledge](knowledge.md) | Confluence, Notion | 49 |
| Marketing | Mailchimp, SendGrid | 43 |
| Networking | ALB, CloudFront, Route53 | 43 |
| [Storage](storage.md) | Google Drive, S3 | 42 |
| Message Queue | RabbitMQ, SQS | 37 |
| Analytics | Mixpanel, Segment | 28 |
| E-Commerce | Shopify | 27 |
| Social | LinkedIn, Medium, X | 21 |
| Custom | Webhook | 12 |

## Authentication

All connectors follow the BYOK (Bring Your Own Key) model. You provide API tokens, OAuth access tokens, or API keys directly. ToolsConnector never stores, manages, or exchanges credentials on your behalf.

See the [Credentials Guide](../guides/credentials.md) for details on authentication patterns for each connector.
