# Changelog

All notable changes to ToolsConnector are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-19

### Added

- **3 social publisher connectors** for content workflows:
  - `linkedin` — 8 actions for posts, comments, reactions on personal feed.
    Auth: OAuth 2.0 Bearer token with `openid profile email w_member_social r_member_social` scopes.
    Uses `/rest/posts` (with `LinkedIn-Version: 202506` header) for posts and
    `/v2/socialActions` for comments and reactions.
    DMs and mentions are out of scope — they require LinkedIn Partner Program
    approval (a contract, not OAuth scopes) and are not BYOK-accessible.
    Token expiry (60 days) raises `TokenExpiredError` with a clear hint.
  - `x` (Twitter) — 9 actions for tweets, threads, replies, likes, mentions, DMs.
    Auth: OAuth 2.0 Bearer token (user context).
    Free tier covers all write actions; `list_mentions` and `send_dm` require
    Basic tier ($100/mo). Tier-gated 403 responses are mapped to
    `PermissionDeniedError` with a friendly upgrade hint.
    `create_thread` posts sequentially with partial-success visibility:
    on failure, posted-so-far tweets are preserved on `e.details["posted_tweets"]`.
  - `medium` — 4 actions for publishing to personal feed and publications.
    Auth: Bearer integration token. NOTE: Medium API was deprecated for new
    tokens in 2023; this connector works only for users with existing legacy
    tokens. Comments and post listing are out of scope (Medium API does not
    provide them; RSS scraping rejected as TOS-violating).

- **`[publishers]` install bundle**: `pip install "toolsconnector[publishers]"`
  installs all three together for content-workflow agents.

- **`ConnectorCategory.SOCIAL`** put into active use for the first time
  (was reserved in the enum, now used by linkedin/x/medium).

### Stats

- 68 connectors (↑ from 65), 1,370 actions (↑ from 1,349)
- All three new connectors register in `_KNOWN_CONNECTORS`, generate static
  HTML pages with JSON-LD + sitemap entries, and are MCP-served via the
  fixed JSON-Schema-derived handler signatures (#1).

## [0.2.1] - 2026-04-16

### Fixed

- **Critical MCP fix**: handler `__signature__` now built from the tool's JSON Schema instead
  of using bare `(**kwargs: Any)`. A `**kwargs` signature caused FastMCP to emit a single
  opaque `kwargs: object` parameter in the MCP schema and route all LLM arguments as
  `_handler(kwargs={...})` — wrapping args one level too deep, breaking every tool call with
  `TypeError: method() got an unexpected keyword argument 'kwargs'`.
  Affects both `ToolKit.serve_mcp()` and `MCPServer`. Closes #1.

## [0.2.0] - 2026-04-16

### Added

- **14 AWS connectors** — full infrastructure lifecycle management for AI agents:
  - `cloudfront` — 10 actions (distributions, invalidations, config)
  - `ecr` — 12 actions (repositories, images, lifecycle policies, auth tokens)
  - `ecs` — 25 actions (clusters, services, task definitions, tasks, capacity)
  - `ec2` — 30 actions (instances, security groups, key pairs, elastic IPs, VPCs, AMIs)
  - `alb` — 18 actions (load balancers, target groups, listeners, rules, health checks)
  - `route53` — 15 actions (hosted zones, DNS records, health checks)
  - `acm` — 10 actions (SSL certificates, validation, tagging)
  - `cloudwatch` — 20 actions (metrics, alarms, dashboards, log groups, log events)
  - `iam` — 20 actions (roles, policies, instance profiles, access keys, users)
  - `secrets_manager` — 12 actions (secrets CRUD, rotation, random password)
  - `rds` — 25 actions (DB instances, clusters, snapshots, replicas, subnet groups)
  - `lambda_connector` — 15 actions (functions, invocation, versions, aliases, permissions)
- **`connectors/_aws/` shared foundation** — zero duplication across all 14 AWS connectors:
  - `auth.py` — `AWSCredentials` + `parse_credentials()` supporting 5 input formats
    (JSON dict, colon-separated string, env vars, AWS profile, STS session token)
  - `signing.py` — generic `sign_v4(service=...)` (service was hardcoded `"s3"` before)
  - `client.py` — `AWSBaseClient` with 3 API patterns: REST, JSON Target, Query+XML
  - `errors.py` — structured AWS error parsing for JSON and XML error responses
  - `regions.py` — `get_endpoint()` with global service handling (IAM, Route53, CloudFront)
  - `xml_helpers.py` — generic XML parsing utilities
- **AWS install bundles**: `[aws-deploy]`, `[aws-infra]`, `[aws-monitor]`, `[aws-data]`, `[aws]`
- **New ConnectorCategory values**: `COMPUTE`, `NETWORKING`
- **Static documentation site**: 65 pre-generated connector pages at `/connectors/{name}/`
  with full action tables, JSON-LD structured data, and install instructions
- **SEO**: Open Graph, Twitter Cards, JSON-LD (SoftwareApplication + FAQPage), sitemap.xml,
  robots.txt, OG image (1200×630), per-route dynamic meta updates

### Changed

- S3 connector migrated to use shared `_aws/` signing and credential parsing
- SQS connector migrated to use shared `_aws/` signing (removed 82-line duplicate SigV4)
- `s3` and `sqs` extras no longer incorrectly list `boto3` as a dependency

### Fixed

- MCP server handler: renamed `_tn` → `tn` closure parameter — FastMCP rejected any
  parameter starting with `_`, causing `InvalidSignature` on all tool registrations

### Stats

- **65 connectors** (up from 53), **1,349 actions** (up from 1,137)
- **14 AWS connectors** covering the full deploy → operate → monitor lifecycle
- **Zero new external dependencies** — all AWS connectors use raw httpx + SigV4

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
