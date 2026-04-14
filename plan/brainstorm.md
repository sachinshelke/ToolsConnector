# ToolsConnector — Complete Brainstorming Document

> **Date:** April 2, 2026  
> **Status:** Brainstorming — Pre-Architecture Phase  
> **Participants:** Sachin (Founder) + AI Pair (Antigravity)  
> **Goal:** Establish the vision, stress-test every assumption, document all debates and reasoning, and solidify architecture principles before any code is written.

---

## Table of Contents

1. [The Problem Statement](#1-the-problem-statement)
2. [Competitive Landscape Deep-Dive](#2-competitive-landscape-deep-dive)
3. [Vision & Positioning Debate](#3-vision--positioning-debate)
4. [The Kafka Open-Source Model](#4-the-kafka-open-source-model)
5. [Language Strategy Debate](#5-language-strategy-debate)
6. [The Auth Debate](#6-the-auth-debate)
7. [The Wrapper Tax Debate](#7-the-wrapper-tax-debate)
8. [The Interface Depth Debate](#8-the-interface-depth-debate)
9. [The Package Structure Debate](#9-the-package-structure-debate)
10. [Quality Control Debate](#10-quality-control-debate)
11. [Legacy vs AI-Native Debate](#11-legacy-vs-ai-native-debate)
12. [AI Tool Selection Scope Debate](#12-ai-tool-selection-scope-debate)
13. [The Connector Health Agent System](#13-the-connector-health-agent-system)
14. [Observability — Included or Not?](#14-observability--included-or-not)
15. [MCP Strategy](#15-mcp-strategy)
16. [Architecture — Final Shape](#16-architecture--final-shape)
17. [Connector Authoring Experience](#17-connector-authoring-experience)
18. [How Different Consumers Use It](#18-how-different-consumers-use-it)
19. [Realistic Tool Scope](#19-realistic-tool-scope)
20. [Differentiators Summary](#20-differentiators-summary)
21. [Open Items Requiring Further Discussion](#21-open-items-requiring-further-discussion)
22. [Success Criteria](#22-success-criteria)

---

## 1. The Problem Statement

### The Initial Framing

There are many agentic frameworks and people are creating AI agents, AI platforms, and many things on top of AI. But whenever they need to connect with different tools, they have to build it from scratch. Each platform has its own structure or design to connect the tools. However, every tool connects in the same way — the only part that changes is the internal architecture or design philosophy of each platform.

### What "Tools" Means in This Context

Tools = external services and platforms that applications/agents need to interact with:
- **Communication:** Gmail, Slack, Discord, Microsoft Teams
- **Project Management:** Jira, Asana, Linear, Trello
- **Code Platforms:** GitHub, GitLab, Bitbucket
- **Storage:** Google Drive, Dropbox, S3, OneDrive
- **Knowledge:** Notion, Confluence, Coda
- **Databases:** PostgreSQL, MySQL, MongoDB, Redis
- **CRM:** Salesforce, HubSpot, Pipedrive
- **DevOps:** Kubernetes, Docker, AWS, GCP
- **And hundreds more...**

Every one of these tools has exposed their SDK, library, APIs, CLI, and many other interfaces. The connection patterns are fundamentally the same — authenticate, call API, handle response, manage errors.

### The Core Insight

**The tool integration itself is platform-agnostic.** Sending an email via Gmail is the same whether you're doing it from LangChain, CrewAI, AutoGen, a Flask app, or a cron job. The only thing that differs is how each consuming platform expects the tool to be wrapped/presented.

### What Doesn't Exist Today

There is no open-source, self-contained, plug-and-play library that:
- Works for both traditional applications AND AI agents
- Requires no cloud dependency or hosted service
- Provides a unified interface across all tools
- Auto-generates MCP servers, function calling schemas, etc.
- Is community-driven with quality gates
- Can become an industry primitive/standard

### The "Why Not Just AI-Generate It" Fallacy

In the era of advanced AI, developers often ask: *"Why use a library when Claude or Cursor can generate a Gmail OAuth wrapper in 5 minutes?"*

**The reality:** 
- **Token efficiency and correctness:** Generating reliable code repeatedly wastes tokens, and AI can hallucinate specs if upstream APIs have recently changed. 
- **The Maintenance Nightmare:** Code generation is easy; maintenance is hard. Who updates the generated code when the API changes? Who ensures high-performance pagination, security, and edge-case testing?
- **Third-Party Avoidance:** Developers don't want to rely on closed, third-party managed integration platforms (like Composio) that lock them in or require paid subscriptions.
- **The Agent Army Solution:** Instead of users generating code on the fly, **we use an AI Agent Army** behind the scenes to build, test, and maintain the connectors offline, embedding that flawless output into our library.

---

## 2. Competitive Landscape Deep-Dive

### 2.1 Model Context Protocol (MCP) — Anthropic

**What it is:** An open-source protocol standard — the "USB-C for AI." Defines a universal way for AI applications to discover and use external tools.

**Strengths:**
- Industry standard for tool discovery and invocation
- Vendor-agnostic, open protocol
- Growing adoption across AI tools (Claude, Cursor, etc.)
- Good for interoperability

**Weaknesses:**
- **No auth handling** — MCP doesn't manage OAuth, API keys, or token lifecycle
- **No pre-built connectors** — You have to write MCP servers from scratch
- **Token overhead** — Tool definitions can consume 40-50% of context window
- **Security gaps** — No built-in identity management, vulnerable to prompt injection and tool shadowing
- **State management complexity** — Stateful sessions conflict with stateless microservices
- **Not an agent framework** — No agent-to-agent communication, no portable identity, no enforceable policy

**Key criticism (2026):** MCP solved tool discovery but not the tool integration problem itself. Some advanced builders are moving to direct API calls, arguing MCP is an unnecessary abstraction for high-scale environments.

### 2.2 Composio — Integration Platform

**What it is:** A hosted platform providing an "action layer" for AI agents with 500+ managed integrations.

**Strengths:**
- Large connector ecosystem (500+ tools)
- Managed authentication (OAuth flows handled for you)
- AI-native SDKs designed specifically for LLM tool calling
- Native MCP support
- Handles "plumbing" — auth, token management, reliable execution

**Weaknesses:**
- **Vendor lock-in** — Hosted service, requires their cloud
- **Proprietary** — Not truly open source in a meaningful sense
- **Only works for AI** — Not useful for traditional applications
- **Cost** — Managed service = ongoing cost
- **Dependency risk** — If Composio goes down, your agents can't use tools

### 2.3 Nango — Auth Infrastructure

**What it is:** Open-source core focused on OAuth and integration infrastructure.

**Strengths:**
- Open-source core
- Developer-first, high control and observability
- Strong at OAuth management and data synchronization
- Self-hosting options for enterprise security
- OpenTelemetry traces

**Weaknesses:**
- **Focused on auth, not tool actions** — Doesn't provide pre-built tool implementations
- **Complex setup** — More infrastructure than library
- **Primarily for ongoing data sync** — Not optimized for on-demand tool calling

### 2.4 Paragon — Embedded iPaaS

**What it is:** Integration platform targeting SaaS companies that need to ship integrations to their end-users.

**Strengths:**
- Visual workflow builder
- White-labeled UI components for embedding
- Both low-code and pro-code approaches
- ActionKit for agent tool calling

**Weaknesses:**
- **SaaS-only focus** — Not a general-purpose tool
- **Proprietary** — Closed source
- **Expensive** — Enterprise pricing
- **Not a library** — Can't `pip install` and use

### 2.5 Raw SDKs (google-api-python-client, slack-sdk, etc.)

**Strengths:**
- Full control, officially maintained by tool vendors
- Complete feature coverage
- Direct, no abstraction layer

**Weaknesses:**
- **Each is different** — No unified interface, patterns, or conventions
- **No AI-native features** — No schema generation, no tool descriptions for LLMs
- **Fragmented** — Managing 10 different SDK styles in one project is painful
- **No built-in retries, rate limiting, pagination consistency**

### 2.6 The Gap in the Market

```
                    Works for AI    Works for Legacy    Open Source    Self-Hosted    Unified Interface
MCP                      ✅              ❌                ✅             ✅              ✅ (protocol)
Composio                 ✅              ❌                ❌             ❌              ✅
Nango                    Partial         Partial           ✅             ✅              ❌ (auth only)
Paragon                  Partial         ❌                ❌             ❌              ✅
Raw SDKs                 ❌              ✅                ✅             ✅              ❌
ToolsConnector (ours)    ✅              ✅                ✅             ✅              ✅
```

**No existing solution covers all five requirements.** That's the gap.

---

## 3. Vision & Positioning Debate

### Initial Framing: "A plug and play library"

The first idea was simple: a library anyone can install and use to connect to tools. Like an npm package or pip package that just works.

### Evolution: "A primitive, not a platform"

During discussion, the vision evolved significantly. The initial "library" framing was too small. The insight was:

**ToolsConnector should be a primitive — a foundational building block that other platforms build upon.**

### The Debate: Library vs Primitive vs Platform

| Approach | What it means | Risk |
|---|---|---|
| **Library** | pip install, use in your code | Too small; doesn't become a standard |
| **Primitive** | Foundational building block others depend on | Right ambition; hard to execute |
| **Platform** | Hosted service with dashboard, auth | Becomes another Composio; loses open-source soul |

**Conclusion:** Primitive is the right positioning. Like HTTP, Docker, Redis — it does one thing perfectly and lets others build on top.

### The Dual-Use Principle (Critical Insight)

**Debate:** Should ToolsConnector target only AI agents, or also traditional applications?

**Argument for AI-only:**
- Focused positioning
- AI market is growing fastest
- Can optimize for agent use cases

**Argument for dual-use (AI + legacy):**
- If it only works for AI, it's a niche tool
- If it works for everyone AND is AI-supercharged, it becomes the standard
- Larger addressable market = more contributors
- Legacy developers today become AI developers tomorrow
- A Flask developer automating email reports uses the same Gmail connector that a CrewAI agent uses

**Decision: Dual-use.** The same connector works for a cron job, a backend service, a traditional app, an AI agent, and an AI platform. The AI-native features (tool selection, MCP serving, schema generation) are additive — you don't need them for traditional use.

```
Traditional Developer                    AI Agent
        │                                    │
        │  from toolsconnector import Gmail  │
        │  gmail = Gmail(api_key="...")       │
        │  gmail.send_email(to=..., body=..) │
        │                                    │
        ▼                                    ▼
   Same connector.                   Same connector.
   Used directly.                    Used via MCP / function calling.
   No AI needed.                     AI-native descriptions built-in.
```

### Why "Primitive" Matters

What made other tech become primitives:
- **HTTP** — didn't tell you how to build your app, just how to communicate
- **Docker** — didn't tell you how to deploy, just how to package
- **OpenAPI/Swagger** — didn't build your API, just defined the spec
- **Redis** — didn't build your cache layer, just gave you the fastest building block

**The pattern:** A primitive defines a contract and does one thing perfectly. It's unopinionated about everything else.

---

## 4. The Kafka Open-Source Model

### The Analogy

**Kafka** is fully open-source, but there are companies that manage the Kafka infrastructure. ToolsConnector should follow this model:

- **Core is fully open-source** (Apache-style license)
- **Confluent** built a business managing Kafka
- **AWS MSK**, **Aiven**, **RedPanda** all emerged around the ecosystem
- The ecosystem grew *because* the core was genuinely useful and unopinionated

### For ToolsConnector

- Build the best open-source core
- Managed offerings naturally follow — LiminaHub or anyone else can build a hosted version
- Companies can embed ToolsConnector in their products
- The key is making the core so good it becomes the **default choice**

### Revenue Path (Not Primary Concern Now, but Important)

The open-source core doesn't need to generate revenue by itself. Sustainability can come from:
- Managed service offerings (like Confluent for Kafka)
- Enterprise features (advanced security, governance, audit logs)
- Support contracts
- Contributions from companies who benefit from the ecosystem

**But:** Revenue is a later-stage concern. The priority is making the core indispensable.

---

## 5. Language Strategy Debate

### Approach 1: Python Only

**For:**
- 90%+ of AI agent frameworks are Python (LangChain, CrewAI, AutoGen, PydanticAI, AgentScope)
- Fastest path to community adoption in the AI space
- One language = easier to maintain

**Against:**
- Excludes TypeScript/Node.js ecosystem (Vercel AI SDK, Mastra)
- Some tools are primarily JavaScript-oriented

### Approach 2: Multi-Language from Day One

**For:**
- Broader reach immediately
- No one feels excluded

**Against:**
- 2x maintenance burden from day one
- Slower development speed
- Difficult for a small team

### Approach 3: Python First, Spec-Driven (Chosen)

**For:**
- Start with Python for immediate AI community traction
- TypeScript as fast second
- But the **connector definitions** (schemas, action descriptions, auth configs) are stored in a **language-agnostic format**
- Code generators can target any language from the spec
- Contributors write the spec + one implementation; other language impls can be generated or hand-written

**Against:**
- Spec format adds design complexity upfront
- Generated code may not feel native

**Decision: Python first with language-agnostic specs.** But also pragmatic — "tools require any language, we have to provide support where that tool can support, but one step at a time."

### Version Compatibility

**Debate:** What minimum Python version?
- 3.8+ → Maximum compatibility but limits modern features
- 3.10+ → Good balance, match types work
- 3.12+ → Newest features but excludes many projects

**Leaning:** 3.9+ as a practical balance. Supports type hints, Union syntax, and most modern patterns without excluding legacy projects.

---

## 6. The Auth Debate

This was one of the most consequential discussions. Auth is where most tool connector projects either succeed or get stuck.

### The Initial Question

"Who manages OAuth tokens? The developer? An optional companion service?"

### Sachin's Position

> "Why do we need auth? People can configure their own auth key as it is just a library or service. We need to make sure that if any keys are provided they should be securely stored. And we can provide option to bring their own key store as well."

> "Redirect URL is correct but we are providing a tools connector. That configuration anyway they have to do as it's their product, not ours. We are providing a library or SDK. But the protocol should be handled in the tools connector."

### The Problem With Auth

Not all auth is simple. There's a spectrum:

```
Simple ◄──────────────────────────────────────────────────► Complex

API Keys          Personal Access    OAuth2           Enterprise SSO
(OpenAI,           Tokens             (Gmail,          (SAML, Active
 SendGrid)         (GitHub, Jira)      Slack,           Directory)
                                       Notion)
```

- **API keys / tokens:** User provides a string. Library stores it. Done. ✅
- **OAuth2:** Requires redirect URLs, consent flows, token exchange, token refresh, scope management. This is inherently a server-side concern.
- **Enterprise SSO:** Requires SAML/OIDC integration. Very complex.

### Approach 1: BYOT (Bring Your Own Token) Only

"Get your OAuth token elsewhere, give it to us."

**For:**
- Simplest to implement
- No server component needed
- Clean separation of concerns

**Against:**
- Pushes complex OAuth work onto the developer
- Poor developer experience for OAuth-based tools
- Every developer reinvents the OAuth dance

### Approach 2: Full OAuth Management (Like Composio)

Run a server that handles OAuth flows, redirect callbacks, token storage.

**For:**
- Best developer experience
- Handles the hard parts

**Against:**
- Makes the library into a service/platform
- Requires hosting infrastructure
- Exactly what Composio does — we become another Composio

### Approach 3: Protocol Handler with BYOK (Chosen)

Split the responsibility clearly:

**Developer's responsibility (their product):**
- Register OAuth app with the provider (get client_id, client_secret)
- Set up redirect URLs in their infrastructure
- Handle the consent screen (user clicks "authorize")
- Provide credentials/tokens to ToolsConnector

**ToolsConnector's responsibility (our library):**
- Token exchange (authorization code → access token)
- Token refresh (handle expiry automatically)
- Token storage (via pluggable keystore)
- Scope management (know what permissions each action needs)
- Protocol quirks (each provider implements OAuth slightly differently — we abstract that)

**Rationale:** The developer owns the config (it's their product). We own the protocol handling (that's our library's job). Nobody needs to run a hosted service.

```python
gmail = Gmail(
    client_id="their-client-id",
    client_secret="their-secret",
    refresh_token="obtained-from-their-oauth-flow"
)
# From here, ToolsConnector handles refresh automatically
```

### Pluggable KeyStore

For secure storage, provide pluggable backends:

```python
from toolsconnector.keystore import LocalKeyStore, VaultKeyStore

# Simple: local encrypted file (default)
tc = ToolsConnector(keystore=LocalKeyStore("~/.toolsconnector/keys"))

# Enterprise: HashiCorp Vault
tc = ToolsConnector(keystore=VaultKeyStore(vault_url="..."))

# Cloud: AWS Secrets Manager
tc = ToolsConnector(keystore=AWSKeyStore(region="us-east-1"))

# Custom: bring your own implementation
tc = ToolsConnector(keystore=MyCustomKeyStore())
```

The keystore interface is simple — `get(key)`, `set(key, value)`, `delete(key)` — so anyone can implement a custom backend.

---

## 7. The Wrapper Tax Debate

This is about how connectors interact with underlying tool APIs. It has massive maintenance implications.

### The Problem

If we wrap official SDKs (`google-api-python-client`, `slack-sdk`):
- Every time Google updates their SDK, our connector lags or breaks
- We're forever chasing upstream changes
- Developers may ask "why not just use the official SDK directly?"

If we DON'T use official SDKs and call APIs directly via raw HTTP:
- We're maintaining HTTP clients for 100+ services
- That's an enormous maintenance burden

### Approach 1: Wrap Official SDKs

```python
# Our connector wraps google-api-python-client
class Gmail(Connector):
    def list_emails(self, ...):
        return self.client.users().messages().list(...).execute()
```

**For:**
- Feature-complete immediately
- Maintained by tool vendors
- Battle-tested code

**Against:**
- SDK breaking changes cascade to our connectors
- SDK updates require our connector updates
- Adds SDK as dependency (increases package size)
- Some SDKs are poorly maintained

### Approach 2: Raw HTTP Calls

```python
# Our connector calls the Gmail REST API directly
class Gmail(Connector):
    def list_emails(self, ...):
        return self.http.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", ...)
```

**For:**
- No SDK dependency
- Full control over behavior
- Lighter weight

**Against:**
- Massive maintenance burden at scale
- Rebuilding what SDKs already do
- Has to handle every API quirk manually

### Approach 3: Generate from OpenAPI Specs

```yaml
# Auto-generate connectors from published OpenAPI specs
openapi: 3.0.0
paths:
  /gmail/v1/users/me/messages:
    get:
      operationId: listMessages
      ...
```

**For:**
- Automated, potentially always up-to-date
- Most major services publish OpenAPI specs

**Against:**
- Not all tools publish OpenAPI specs (many don't)
- Generated code quality varies
- Doesn't capture tool-specific logic (pagination styles, error formats, etc.)
- Loses the "handcrafted" quality

### Approach 4: Interceptor Philosophy (Sachin's Input)

> "What about something like an interceptor of network calls which automatically captures the data?"

This isn't literal, but the philosophy is: **make the connection so automatic that the connector barely needs maintenance.** Ideas this inspires:
- Auto-discovery of API endpoints from documentation
- AI-assisted connector generation from API docs
- Runtime API response analysis to detect changes

### Resolution: Hybrid Approach + Health Agent

**Decision:** Use the best approach per connector:
- **Stable SDKs (Google, AWS, Slack):** Wrap the official SDK — it's maintained, feature-complete, and battle-tested
- **No SDK available:** Raw HTTP with clean abstractions
- **OpenAPI available:** Supplementary generation for boilerplate
- **Health Agent:** Automated monitoring of upstream changes to keep everything current (see Section 13)

**Key point from Sachin:**
> "SDK update by Google will definitely be chaos, but who will maintain it? Google itself or contributors? Someone has to update it. As it is open source, initially I might need to take care, but I need to have automated alerts about what's updated so that we can handle it automatically."

This led to the Connector Health Agent concept (Section 13).

---

## 8. The Interface Depth Debate

### The Problem

If we standardize the interface, we lose tool-specific features. Gmail has labels, stars, threads, drafts, filters, forwarding, delegate access. This isn't just about Gmail — it applies to ALL tools.

### Approach 1: Simplified Interface (Least Common Denominator)

Only expose the most common actions across similar tools.

```python
# Every communication tool has: send_message, list_messages
gmail.send_message(to=..., body=...)
slack.send_message(channel=..., text=...)
```

**For:**
- Clean, simple, easy to learn
- Portable between similar tools

**Against:**
- Power users leave ("I'll just use the official SDK")
- Can't access tool-specific features (Gmail labels, Slack threads)
- "Lowest common denominator" never satisfies anyone

### Approach 2: Two-Tier Interface

```python
# Tier 1: High-level (80% use cases)
gmail.list_emails()

# Tier 2: Full access (power users)
gmail.raw_client.users().messages().list(userId="me", q="...").execute()
```

**For:**
- Both simple and powerful
- Escape hatch for advanced needs

**Against:**
- Tier 2 loses all framework adapters, schema generation, type safety
- Developers on Tier 2 are essentially using the raw SDK with extra steps
- Breaks the "unified interface" promise

**Sachin's pushback:**
> "It's not only about Gmail, this can be with all other tools as well. We need to think about it with a new and creative approach but the approach has to be seamless."

### Approach 3: Full Capability with Consistent Patterns (Chosen)

**Don't simplify the tool. Make the complex tool SAFE to use.**

Every connector exposes the tool's **full capability**, not a dumbed-down subset. But it adds value through:

1. **Consistent patterns** — Pagination works the same in Gmail, Slack, and Jira. Filtering works the same. Error handling works the same. Retry/rate-limiting works the same. The API underneath is different, but the developer experience is identical.

2. **Type safety** — Every input and output is typed. You can't pass a wrong parameter. Your IDE autocompletes everything.

3. **Smart defaults** — The most common usage is one line. Advanced usage is possible but not required. Same interface, not a separate tier.

```python
# Simple — smart defaults handle the rest
emails = gmail.list_emails()

# Advanced — full power available, same interface, same type safety
emails = gmail.list_emails(
    query="from:boss@company.com has:attachment",
    labels=["INBOX"],
    include_spam_trash=False,
    page_size=50,
    fields=["id", "subject", "from", "date", "snippet"]
)
```

**Why this works:**
- Gmail might have 50 actions and that's fine
- Slack might have 80 actions and that's fine
- The power isn't in reducing the surface — it's in making the surface **consistent and safe across all tools**
- A developer who knows how to paginate in Gmail automatically knows how to paginate in Slack
- IDE autocomplete guides you through every option

---

## 9. The Package Structure Debate

### The Problem

If someone wants to use only Gmail and Slack, should they install all 1000+ connectors?

### Approach 1: Monorepo — One Package

```bash
pip install toolsconnector  # Gets everything
```

**For:**
- Simple installation
- One version to track
- Easy discoverability

**Against:**
- Massive package size with 1000+ connectors
- Pulls in dependencies for tools you'll never use
- Version bump for one connector affects all

### Approach 2: Polyrepo — Separate Packages

```bash
pip install toolsconnector-gmail
pip install toolsconnector-slack
```

**For:**
- Independent versioning per connector
- Minimal dependencies

**Against:**
- Discoverability nightmare
- Complex dependency management
- Lots of PyPI packages to maintain

### Approach 3: Bundle with Extras (Chosen)

```bash
# Just core (for connector authors)
pip install toolsconnector

# Individual tools
pip install "toolsconnector[gmail]"
pip install "toolsconnector[slack]"

# By category
pip install "toolsconnector[google]"           # All Google tools
pip install "toolsconnector[communication]"    # Slack, Discord, Teams, email
pip install "toolsconnector[project-mgmt]"     # Jira, Asana, Linear

# Everything
pip install "toolsconnector[all]"
```

**Sachin's input:**
> "It may look complicated but I think it will give flexibility to developers to use it as they want, rather than increasing library size for 1000+ connectors where they want to use only 2."

**Why this works:**
- Single package with optional extras (Python's extras_require)
- Each connector declares its own dependencies
- Installing `[gmail]` pulls in `google-api-python-client`
- Installing `[slack]` pulls in `slack-sdk`
- Core stays lightweight
- Developers only pay (in dependency weight) for what they use
- Categories provide convenience without forcing everything

---

## 10. Quality Control Debate

### The Problem

Community contributions sound great, but who ensures a community-contributed Salesforce connector is production-quality? At scale (500+ connectors), human review is a full-time job.

### Approach 1: Linux Kernel Model (Strict Gatekeeping)

Maintainers review everything, strict quality bar.

**For:**
- High quality guaranteed
- Consistent patterns

**Against:**
- Slow contribution velocity
- Bottleneck on maintainer capacity
- Discourages community participation

### Approach 2: npm Model (Open Publishing)

Anyone publishes anything.

**For:**
- Fast, lots of contributions
- No bottleneck

**Against:**
- Quality varies wildly
- Security risks
- Broken connectors damage trust

### Approach 3: Official Tiers + AI-Assisted Review (Chosen)

**Two-tier connector system:**
- **Official connectors:** Maintained by core team, highest quality, 20-30 most-used tools
- **Community connectors:** Contributed by companies/developers, AI-assisted quality review

**Sachin's insight:**
> "Nowadays, all companies' quality checklists LLM models know. We have to use AI to check the control. Also every company has their documentation for quality control — at least for those who are providing tools."

**The AI-assisted quality gate:**
- LLM-powered review checks connector PRs against quality checklist
- Validates type safety, error handling patterns, documentation coverage
- Runs automated tests against sandbox APIs
- Reads official tool documentation to verify correctness
- Flags deviations from connector SDK patterns

**Why this works:**
- AI handles routine quality checking at scale
- Core team focuses on architectural review, not line-by-line code review
- Companies contributing connectors follow published documentation
- Community connectors can be "promoted" to official once they prove reliability

---

## 11. Legacy vs AI-Native Debate

### The Tension

Legacy projects want:
- Stability, backward compatibility, minimal dependencies
- Older Python version support
- No bleeding-edge features
- Synchronous by default

AI-native features want:
- Type hints everywhere, Pydantic models, async-first
- Modern Python (3.10+), latest patterns
- Schema generation, tool descriptions for LLMs

These pull in opposite directions.

### Approach 1: AI-Native Only

Target modern Python, async-first, full type hints. Tell legacy projects "upgrade."

**For:**
- Cleaner codebase
- Best AI developer experience

**Against:**
- Excludes large segment of potential users
- Hurts adoption

### Approach 2: Legacy-First

Maximize backward compatibility. No modern Python features.

**For:**
- Maximum reach

**Against:**
- Cripples AI-native features
- Feels outdated

### Approach 3: Modern Core with Legacy Compatibility (Chosen)

**Sachin's insight:**
> "Here is where our expertise and uniqueness comes. If we want to make a change we need to support for some time a legacy structure. Eventually as and when people move to AI, legacy won't be required."

**Decision:**
- Core is modern Python (3.9+, rich type hints)
- Sync and async interfaces both supported
- AI-native features (schema generation, tool descriptions) are always available — they don't require the user to be building an AI app
- Legacy projects use it as a clean, typed library
- AI projects use the same library with AI features turned on
- Over time, as the ecosystem modernizes, legacy concerns naturally fade

---

## 12. AI Tool Selection Scope Debate

### The Original Idea

If you have 500 tools loaded, the AI agent shouldn't get all 500 in its context. The library should help select the right 3-5 tools for the current task.

```python
kit = ToolKit([Gmail, Slack, Notion, Jira])
relevant = kit.select("reply to the email from John and post a summary in #general")
# Returns: [Gmail, Slack]
```

### The Problem

This requires:
- Embedding all tool descriptions (needs an embedding model)
- A ranking/retrieval system
- This adds AI dependencies (`torch`, `openai`, etc.) to what should be a lightweight library
- Someone installing `toolsconnector` for a cron job shouldn't download PyTorch

### The Counter-Argument

**Sachin's practical point:**
> "Nobody is going to use 1000+ tools. People will configure 5 to 6 or 10 to 20 as per their need. Many tools are similar — Asana vs Jira, GitHub vs Bitbucket. Be practical — as much as tools are not free or open source. Salesforce won't work without enterprise credentials."

This changes the framing. The problem isn't "select 5 from 500 at runtime." It's:
- People configure 5-20 tools for their deployment
- The tool selection problem is much smaller
- The MCP server just needs to know which tools are configured

### Resolution

**Decision:** Smart tool selection is a separate package (`toolsconnector-mcp`), NOT core.

- **Core library:** You configure the tools you want. No AI selection needed.
- **toolsconnector-mcp:** For AI platforms, provides MCP server generation + optional smart selection for larger deployments.
- Most practical deployments have 5-20 tools — selection is trivial at that scale
- For the rare case with 100+ tools configured, the MCP package handles it

---

## 13. The Connector Health Agent System

### Origin

**Sachin's input:**
> "I need to have automated alerts about what is updated so that we will do it automatically. Also we need to have some agent team in our code base so that it will run and identify the updates. Similar to Claude agent team."

### The Concept

An automated system (an "AI agent team") that monitors upstream APIs/SDKs for changes and helps keep connectors up to date. No other open-source tool library does this today.

### How It Works

```
┌──────────────────────────────────────────────────────────────┐
│                   CONNECTOR HEALTH AGENT                      │
│                                                              │
│  WATCH LAYER  (runs on schedule — daily/weekly)              │
│  ├── Monitor OpenAPI spec URLs for diffs                     │
│  ├── Watch GitHub releases of official SDKs                  │
│  ├── Monitor API changelog pages (scrape/RSS)                │
│  ├── Track deprecation notices                               │
│  └── Run automated integration tests against sandbox APIs    │
│                                                              │
│  DETECT LAYER                                                │
│  ├── AI agent reads the diff / changelog / release notes     │
│  ├── Classifies: breaking change / new feature / deprecation │
│  │   / rate limit change / no impact                         │
│  └── Maps the change → affected connector code               │
│                                                              │
│  ACT LAYER                                                   │
│  ├── Minor change → Auto-generate a PR with the fix          │
│  ├── Major change → Create issue with analysis + suggested   │
│  │   fix                                                     │
│  └── Critical break → Alert maintainers immediately          │
└──────────────────────────────────────────────────────────────┘
```

### Why This Is a Genuine Differentiator

- **The #1 killer of open-source integration projects is maintenance burden** — connectors go stale
- API changes are mostly predictable patterns (new fields, deprecated endpoints, auth scope changes, rate limit updates)
- An AI agent can handle ~80% of routine updates automatically
- The remaining ~20% (fundamental API redesigns) need human review
- Similar to how Dependabot handles dependency updates, but for API compatibility
- Keeps 500+ connectors fresh without requiring a massive human team

### Implementation Considerations

- Could leverage Claude/GPT agents for changelog reading and code update generation
- Needs sandbox/test accounts for each tool to run integration tests
- Runs as CI/CD pipeline (GitHub Actions or similar)
- Initially manual monitoring, progressively automated as patterns are learned
- **Open question:** How exactly to build this agent team — needs further design work

---

## 14. Observability — Included or Not?

### The Initial Idea

Every tool call emits structured telemetry (using OpenTelemetry). Ship a lightweight usage dashboard.

### Sachin's Pushback

> "Observability could be optional as people might want to use only the connector. Consider that observability might again need to provide auth like Composio is doing. And again we become another Composio or similar tool."

### The Debate

**For including observability:**
- Enterprise users expect it
- Helps with debugging and cost tracking
- OpenTelemetry is lightweight

**Against including observability:**
- The moment we add dashboards and auth for dashboards, we become a platform
- Dashboard auth is a whole separate product
- Bloats the core
- Distraction from the main value: connectors

### Decision: Not in Core

**The core is just the connectors. That's it.**

Observability considerations:
- If someone wants logging, they use Python's standard logging (we emit logs at appropriate levels)
- If someone wants metrics/traces, they instrument it themselves
- If someone wants a dashboard, that's a separate product (could be built by anyone, including as a managed offering)
- We keep the core razor-thin and focused

---

## 15. MCP Strategy

### The Position

> **We don't compete with MCP. We make MCP trivial.**

### The 2026 MCP Reality

As of 2026, MCP (now under the Agentic AI Foundation) is the absolute standard for agent-to-tool communication. Many tool vendors now publish official standalone MCP servers. However, this creates a new problem: **Operational Nightmare**.

Currently, developers are forced to run completely separate, standalone MCP servers for every tool (e.g., a node app for GitHub, a python app for Slack). This leads to fragmented auth management, messy routing, and zero reusability for non-AI code.

### Our Strategy: The Ultimate MCP Factory

**We don't compete with MCP. We make deploying MCP fleets trivial.**

With ToolsConnector, you don't hunt down random standalone MCP servers. You install one library, and it acts as an instant factory to expose your unified tools. All of the operational overhead becomes **one line:**

```python
from toolsconnector.connectors.gmail import Gmail
from toolsconnector.connectors.slack import Slack
from toolsconnector.serve import mcp

# Any connector automatically becomes a fully compliant MCP server
mcp.serve([Gmail, Slack], port=3000)
```

This works because:
- The `@action` decorator already captures tool descriptions and schemas
- Type hints provide input/output schemas
- Auth is already handled by the connector
- Error handling follows our consistent patterns
- The `serve/mcp` module just translates our connector interface → MCP protocol

### Beyond Basic MCP

**Sachin's input:**
> "We might also need our own MCP which can help agents to connect with tools."

This suggests `toolsconnector-mcp` could go beyond just serving MCP:
- **Tool registry:** Know which tools are configured
- **Capability discovery:** What can this set of tools collectively do?
- **Schema optimization:** Minimize token usage in tool definitions
- **Future:** If MCP evolves or is replaced, we adapt the serve layer without changing connectors

---

## 16. Architecture — Final Shape

### Layer Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    TOOLSCONNECTOR STACK                       │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Serve Layer (optional)                                │  │
│  │  MCP Server / REST API / CLI / Function Calling Schema │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────▼───────────────────────────────┐  │
│  │  Connector Runtime                                     │  │
│  │  Consistent patterns: pagination, filtering, errors,   │  │
│  │  retries, rate limiting, type safety                   │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────▼───────────────────────────────┐  │
│  │  Individual Connectors                                 │  │
│  │  Gmail, Slack, Notion, Jira, GitHub, PostgreSQL, ...   │  │
│  │  Each wraps the tool's full capability                 │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────▼───────────────────────────────┐  │
│  │  Core (the primitive)                                  │  │
│  │  BaseConnector, @action decorator, Auth protocol,      │  │
│  │  KeyStore interface, error types, pagination helpers   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─────────────┐  ┌──────────────────────────────────────┐  │
│  │  KeyStore    │  │  toolsconnector-mcp (separate pkg)   │  │
│  │  (pluggable) │  │  MCP server, tool selection,         │  │
│  └─────────────┘  │  advanced AI-native features          │  │
│                    └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Project Structure

```
toolsconnector/
├── core/                    ← The primitive
│   ├── base.py              ← BaseConnector class
│   ├── action.py            ← @action decorator
│   ├── auth.py              ← Auth protocol handling (OAuth2, API key, etc.)
│   ├── types.py             ← Common types (PaginatedList, etc.)
│   ├── errors.py            ← Structured error types
│   ├── pagination.py        ← Consistent pagination patterns
│   └── retry.py             ← Retry and rate limiting
│
├── connectors/              ← Individual tool connectors
│   ├── gmail/
│   │   ├── connector.py     ← Gmail connector implementation
│   │   ├── types.py         ← Gmail-specific types (Email, Label, etc.)
│   │   └── __init__.py
│   ├── slack/
│   ├── notion/
│   ├── jira/
│   ├── github/
│   └── ...
│
├── serve/                   ← Exposure layer
│   ├── mcp.py               ← Auto-generate MCP server from connectors
│   ├── rest.py              ← Expose connectors as REST API
│   ├── cli.py               ← CLI interface
│   └── schema.py            ← Schema generators (OpenAI, Anthropic, Gemini)
│
├── keystore/                ← Pluggable credential storage
│   ├── base.py              ← KeyStore interface
│   ├── local.py             ← Local encrypted file (default)
│   ├── vault.py             ← HashiCorp Vault
│   └── aws.py               ← AWS Secrets Manager
│
└── health/                  ← Connector health agent system
    ├── watcher.py            ← Monitor upstream API/SDK changes
    ├── analyzer.py           ← AI-powered change analysis
    └── reporter.py           ← Generate PRs/issues
```

### Separate AI-Native Package

```
toolsconnector-mcp/              ← Separate pip package
├── server.py                    ← Enhanced MCP server with registry
├── selection.py                 ← Smart tool selection for agents
├── function_calling.py          ← OpenAI/Anthropic/Gemini schema gen
└── registry.py                  ← Tool capability discovery
```

---

## 17. Connector Authoring Experience

### Design Goal

Contributing a new connector should take a single PR with minimal files. If a company can add their tool's connector in an afternoon, contributions flow. If it takes a week, the project dies.

### What a Connector Author Writes

```python
from toolsconnector.core import Connector, action, Auth
from toolsconnector.core.types import PaginatedList

class Gmail(Connector):
    """Connect to Gmail to read, send, and manage emails."""
    
    name = "gmail"
    category = "communication"
    auth_types = [Auth.OAUTH2, Auth.SERVICE_ACCOUNT]
    
    # OAuth configuration — each provider is different, we abstract the quirks
    oauth_config = Auth.OAuth2Config(
        auth_url="https://accounts.google.com/o/oauth2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes={
            "read": ["gmail.readonly"],
            "send": ["gmail.send"],
            "full": ["gmail.modify"]
        }
    )
    
    @action("List emails matching a query")
    def list_emails(
        self, 
        query: str = "is:unread", 
        limit: int = 10,
        labels: list[str] | None = None
    ) -> PaginatedList[Email]:
        """List emails from the user's mailbox.
        
        Args:
            query: Gmail search query (same syntax as Gmail search bar)
            limit: Maximum number of emails to return
            labels: Filter by label IDs (e.g., ["INBOX", "IMPORTANT"])
        """
        response = self.client.users().messages().list(
            userId="me", q=query, maxResults=limit,
            labelIds=labels
        ).execute()
        return PaginatedList(
            items=[Email.from_api(msg) for msg in response.get("messages", [])],
            next_token=response.get("nextPageToken")
        )
    
    @action("Send an email to a recipient", requires_scope="send")
    def send_email(
        self, 
        to: str, 
        subject: str, 
        body: str,
        cc: list[str] | None = None,
        attachments: list[Attachment] | None = None
    ) -> MessageId:
        """Send an email message.
        
        Args:
            to: Recipient email address
            subject: Email subject line
            body: Email body (supports HTML)
            cc: Optional CC recipients
            attachments: Optional file attachments
        """
        message = self._create_message(to, subject, body, cc, attachments)
        result = self.client.users().messages().send(
            userId="me", body=message
        ).execute()
        return MessageId(result["id"])
```

### What the Framework Auto-Generates From This

From the connector code above, ToolsConnector automatically produces:

1. **Typed Python interface** with IDE autocomplete (already there from type hints)
2. **MCP server definition** with tools, descriptions, input/output schemas
3. **OpenAI function calling schema** in JSON
4. **Anthropic tool use schema**
5. **Google Gemini function declarations**
6. **API documentation** from docstrings and type hints
7. **AI-friendly descriptions** from the `@action` annotation + docstrings

**The connector author writes the implementation ONCE. Everything else is derived.**

---

## 18. How Different Consumers Use It

### Traditional Developer (Flask App / Cron Job)

```python
from toolsconnector.connectors.gmail import Gmail

gmail = Gmail(credentials="path/to/service-account.json")

# Daily report emailer — no AI involved, no MCP, just a library
emails = gmail.list_emails(query="from:monitoring@company.com subject:daily-report")
for email in emails:
    process_report(email)
```

### Backend Service (FastAPI)

```python
from toolsconnector.connectors.slack import Slack

slack = Slack(bot_token=os.environ["SLACK_BOT_TOKEN"])

@app.post("/notify")
async def notify_team(message: str):
    await slack.send_message(channel="#alerts", text=message)
    return {"status": "sent"}
```

### AI Platform (MCP Server)

```python
from toolsconnector.connectors.gmail import Gmail
from toolsconnector.connectors.slack import Slack
from toolsconnector.serve import mcp

# Expose tools as MCP server — one line, any AI agent can connect
mcp.serve(
    connectors=[Gmail, Slack],
    port=3000,
    credentials_from="env"
)
```

### AI Agent (Direct Function Calling)

```python
from toolsconnector.connectors.gmail import Gmail
from toolsconnector.serve.schema import to_openai_tools

gmail = Gmail(api_key=os.environ["GMAIL_API_KEY"])

# Generate OpenAI-compatible tool definitions automatically
tools = to_openai_tools([gmail])

# Pass to any LLM
response = openai.chat.completions.create(
    model="gpt-4",
    messages=messages,
    tools=tools   # Auto-generated from type hints + @action
)
```

### LangChain / CrewAI Integration

```python
from toolsconnector.connectors.gmail import Gmail
from toolsconnector.serve.adapters import as_langchain_tools

gmail = Gmail(credentials="...")
tools = as_langchain_tools([gmail])

# Use in any LangChain agent
agent = create_react_agent(llm, tools)
```

### CLI Usage

```bash
# Quick tool testing
$ toolsconnector gmail list-emails --query "is:unread" --limit 5
$ toolsconnector slack send-message --channel "#general" --text "Hello from CLI"
```

---

## 19. Realistic Tool Scope

### The Practical Reality

**Sachin's insight:**
> "Nobody is going to use 1000+ tools. People will configure 5 to 6 or 10 to 20 as per their need. Many tools are similar — for example project management: Asana, Jira, or GitHub and Bitbucket. These are just examples but yes people can use both. Be practical — as much as tools don't come free or open source. Salesforce won't work without enterprise credentials."

### Typical Configuration (8-15 tools per deployment)

```
A typical AI platform / enterprise configures:
├── Communication:    Slack OR Teams (rarely both)
├── Email:            Gmail OR Outlook
├── Project Mgmt:     Jira OR Asana OR Linear
├── Code:             GitHub OR GitLab OR Bitbucket
├── Storage:          GDrive OR Dropbox OR S3
├── Knowledge:        Notion OR Confluence
├── CRM:              Salesforce OR HubSpot
├── Calendar:         Google Calendar OR Outlook Calendar
└── Custom:           Internal APIs via generic HTTP connector
```

### Priority List for v0.1 (First 15-20 Connectors)

> [!IMPORTANT]
> Final list needs validation based on community demand signals.

**Tier 1 — Launch connectors (7):**
1. Gmail
2. Google Drive
3. Slack
4. Notion
5. GitHub
6. Jira
7. Google Calendar

**Tier 2 — Fast follow (6):**
8. Microsoft Outlook / 365
9. Microsoft Teams
10. Confluence
11. Asana
12. AWS S3
13. HubSpot

**Tier 3 — Community-driven (10+):**
14. Salesforce
15. Discord
16. Linear
17. GitLab
18. Stripe
19. Twilio
21. Stripe
22. Twilio
23. SendGrid
24. Airtable
25. Trello

---

## 20. Differentiators Summary

### vs Every Alternative

| Requirement | ToolsConnector | Composio | Raw SDKs | MCP Servers |
|---|---|---|---|---|
| Works without AI | ✅ | ❌ AI-only | ✅ | ❌ |
| Works with AI agents | ✅ | ✅ | ❌ manual | ✅ |
| Self-hosted, no cloud | ✅ | ❌ hosted | ✅ | ✅ |
| Auto-becomes MCP server | ✅ one line | ❌ | ❌ | ✅ (is one) |
| Unified interface | ✅ | ✅ | ❌ fragmented | ❌ fragmented |
| Community-driven OSS | ✅ fully | ❌ proprietary | N/A | fragmented |
| Auto connector maintenance | ✅ Health Agent | ❌ manual | N/A | ❌ manual |
| Pluggable auth/keystore | ✅ | ❌ managed | ✅ | varies |
| Full tool power + consistency | ✅ | ✅ | ✅ full only | varies |
| Works for legacy projects | ✅ | ❌ | ✅ | ❌ |

### The Moat: What Makes Us Uncloneable?

If a tech giant tries to clone this, why would they fail?
1. **The "Automated Maintenance" Advantage:** The #1 killer of integration platforms is API rot. By using our **Connector Health Agent** to constantly crawl APIs and auto-generate PRs for our connectors, we have a structural cost advantage. We can maintain 1,000+ connectors with a 2-person team, while competitors need 50 developers.
2. **Zero-Overhead Primitive:** Competitors like Composio or n8n force traffic through their cloud. We are a stateless, lightweight library that can be embedded anywhere—lambdas, edge functions, local apps.
3. **The "Dual-Use" Community:** By being equally useful for legacy Django/Flask apps and modern AI agents, our user and contributor base is 10x larger. A traditional dev fixing a bug fixes it for the AI community simultaneously.

### The One-Line Pitch

**"If you're building anything that touches external tools — whether it's a cron job, a web app, or an AI agent — you're either using ToolsConnector or you're rebuilding what ToolsConnector already does."**

---

## 21. Open Items Requiring Further Discussion

### 21.1 Naming

"ToolsConnector" is descriptive but long. For a global standard/primitive, shorter names are stickier. Consider:
- Should the name reflect "tools"? "Connect"? "Integration"?
- Or something abstract that becomes its own word (like Docker, Redis, Kafka)?
- Does it need to sound like a standard?

**Context:** OpenAPI doesn't sound like a library. Docker doesn't sound like containerization. Redis doesn't sound like caching. Good names create their own identity.

### 21.2 Error Model Design

How should errors be structured to work for both traditional developers AND AI agents?

**Traditional developers** need: stack traces, error codes, actionable messages
**AI agents** need: structured errors they can reason about and retry

```python
# Possible approach:
ToolError(
    tool="gmail",
    action="send_email",
    code="RATE_LIMITED",
    message="Gmail API rate limit exceeded",
    retry_after_seconds=30,
    suggestion="Wait 30 seconds and retry, or batch remaining emails"
)
```

**Needs design:** What error categories? How detailed? How to make it useful for both humans and AI?

### 21.3 Connector Health Agent — Implementation Details

The concept is defined (Section 13) but needs practical design:
- What AI model powers it? (Claude, GPT, local model?)
- How to get sandbox/test accounts for each tool?
- How to run integration tests in CI/CD without paid accounts?
- What does the "agent team" architecture look like?
- Frequency of monitoring? (daily, weekly, on-demand?)

### 21.4 Testing Strategy for Connectors

- **Unit tests:** Mock API responses, test connector logic
- **Integration tests:** Hit real APIs with sandbox accounts
- **Community contribution testing:** How can contributors test without paid accounts?
- **Contract testing:** Verify connector behavior matches API documentation

### 21.5 License Choice

| License | Enterprise Adoption | Community | Patent Protection |
|---|---|---|---|
| Apache 2.0 | ✅ Best | ✅ Good | ✅ Yes |
| MIT | ✅ Good | ✅ Best (simplest) | ❌ No |
| LGPL | ⚠️ Cautious | ✅ Good | ❌ No |

Apache 2.0 is the most enterprise-friendly and includes patent protection. MIT is simplest but lacks patent grant.

### 21.6 Governance Model

- **Who** are the initial maintainers?
- **How** are architectural decisions made? (RFC process? Core team votes? Benevolent dictator?)
- **Foundation model** (like CNCF/Linux Foundation) vs **company-backed** (like Confluent + Kafka) vs **community-led**?
- When/if to create a formal governance structure?

### 21.7 The "Third Way" for Connector Maintenance — Deeper Exploration

Current decision is "hybrid approach," but needs more concrete guidelines:
- **When to wrap an SDK:** SDK is stable, well-maintained, feature-complete
- **When to use raw HTTP:** No good SDK exists, or SDK is poorly maintained
- **When to auto-generate:** OpenAPI spec is published and stable
- How to decide for new connectors? Need a decision framework.

### 21.8 Async Support Strategy

- Should all connectors support both sync and async?
- Or sync-first with async as optional?
- How to avoid code duplication between sync/async implementations?

### 21.9 Webhook / Event Support

Many tools don't just have request-response APIs. They also push events:
- Slack sends real-time messages via WebSocket
- GitHub sends webhooks on push/PR events
- Jira sends webhooks on issue updates

Should ToolsConnector handle incoming events? Or is that out of scope?

### 21.10 Middleware / Plugin System

Should there be a middleware pipeline for tool calls?
```
auth → rate-limit → retry → log → execute → transform
```
This was discussed early but deprioritized. Still worth exploring for:
- Custom logging
- Cost tracking
- Human-in-the-loop approval
- Caching
- Request/response transformation

### 21.11 File Handling & Object Storage Strategy

File handling (e.g., Slack attachments, Gmail attachments) requires a standardized approach to binary data without bloating LLM context windows or blowing up memory.
**Decision:** We adopt a Bring-Your-Own-Storage (BYOS) model.
- Agents don't pass raw 50MB files in context. They pass reference URIs (e.g., `s3://bucket/file.pdf` or `blob://...`).
- ToolsConnector seamlessly uses storage connectors (AWS S3, Azure Blob, GCS) to resolve these URIs.
- If a specific storage connector isn't available, users can easily build one following ToolsConnector guidelines and publish it.
- The framework automatically streams these URIs into the raw byte streams the target API (like Slack) requires.

---

## 22. Success Criteria

**The project succeeds when:**

1. A developer can `pip install "toolsconnector[gmail]"` and send an email in **under 5 minutes**, with zero prior knowledge of the Gmail API
2. An AI platform can expose ANY installed connector as an MCP server in **one line**
3. Contributing a new connector takes a **single PR** with one Python file
4. At least **5 major AI frameworks/platforms** adopt it as their default tool layer
5. Companies **actively contribute** official connectors for their tools (because being in ToolsConnector = distribution)
6. The Connector Health Agent keeps **80%+ of connectors** passing integration tests without human intervention
7. A traditional Flask/Django developer and a CrewAI agent developer both find it **equally useful**

---

## 23. User Zero: AgentStore & UDAP

Most open-source tools die because they are built in a vacuum. ToolsConnector will be battle-tested immediately inside **AgentStore** and **UDAP**. 

By serving as the fundamental tool layer for a production AI marketplace (AgentStore) experiencing real multi-tenant auth challenges and massive agent volume, ToolsConnector will be hardened against actual enterprise problems before it even launches to the public. AgentStore acts as the ultimate proving ground and credibility anchor.

---

> **Next Steps:** Resolve the open items (Sections 21.1–21.10) and address the architectural gaps (multi-tenancy, type systems, etc.), then proceed to detailed architecture design and connector SDK specification before any coding begins.
