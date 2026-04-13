# Changelog

All notable changes to ToolsConnector are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-05

### Added

- Core primitive: spec/, runtime/, errors/, types/, keystore/
- BaseConnector abstract class with @action decorator
- Auto-generated JSON Schema from type hints and docstrings
- Sync/async bridge: write async, users get both sync and async
- Protocol adapter layer (REST, with GraphQL/SOAP reserved)
- Auth providers: API key, Bearer, OAuth2, Basic
- Middleware pipeline: auth, retry, rate limit, logging
- Pagination strategies: cursor, token, offset
- PaginatedList[T] generic type with auto-pagination
- FileRef + StorageBackend for file handling
- Pluggable KeyStore (InMemory, Environment, LocalFile)
- Full error hierarchy with structured to_dict() for AI consumption
- 53 connectors with 1,137 real actions:
  - Communication: Gmail, Slack, Discord, Outlook, Teams, Twilio, Telegram
  - Code: GitHub, GitLab
  - Project management: Jira, Asana, Linear, Trello
  - Knowledge: Notion, Confluence
  - CRM: HubSpot, Salesforce, Zendesk, Freshdesk, Intercom
  - Finance: Stripe, Plaid
  - Marketing: SendGrid, Mailchimp
  - Storage: Google Drive, S3
  - Database: Supabase, MongoDB, Airtable, Firestore, Redis
  - DevOps: Datadog, PagerDuty, Vercel, Cloudflare, Docker Hub
  - AI/ML: OpenAI, Anthropic, Pinecone
  - Analytics: Mixpanel, Segment
  - Message Queue: SQS, RabbitMQ
  - Security: Okta, Auth0
  - Productivity: Google Calendar, Calendly, Figma
  - E-commerce: Shopify
  - Custom: Generic Webhook
- Serve layer with ToolKit central object:
  - MCP server generation (stdio, SSE, streamable-http)
  - OpenAI function calling schema generator
  - Anthropic tool use schema generator
  - Google Gemini function declaration generator
  - tc CLI command (list, actions, execute, serve)
  - REST API exposure (optional starlette)
- Resilience:
  - Circuit breaker per connector (open/closed/half-open)
  - Pre-validation of arguments against JSON Schema
  - Graceful degradation (one connector fails, others continue)
  - Timeout budget cascading with deadline-aware retries
  - Auto token refresh on TokenExpiredError
  - Dry run mode for dangerous actions
  - Actionable error messages (what, why, how to fix)
  - Structured execution logging
- Tool filtering: include/exclude glob patterns, exclude_dangerous
- Enhanced tool descriptions with connector context prefix
- Agent Army Orchestrator (Claude Agent SDK)
- Architecture FAQ with 15 decision records
- CI/CD with GitHub Actions (lint, test, conformance, security)
