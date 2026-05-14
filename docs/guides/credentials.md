# Credentials Guide

How credentials work in ToolsConnector. Applies to **all** connectors uniformly — Notion, Gmail, GitHub, Slack, Stripe, every one of them.

## The BYOK Philosophy

ToolsConnector follows the Bring Your Own Key (BYOK) model. You register your own OAuth apps, get your own API keys, and choose how to store them. The library handles the protocol (token exchange, refresh, scope validation) but never manages or stores credentials on your behalf.

This design means zero liability for credential storage, full compatibility with enterprise security policies, and no dependency on any hosted service. **ToolsConnector is a primitive** — composition is your application's responsibility. We provide the credential-passing surface; you decide whether tokens come from a config file, a per-request header, a database column, a secrets manager, or anywhere else.

## Three Ways to Provide Credentials

### 1. Programmatic (Inline)

Pass credentials directly when creating a `ToolKit`. Best for code paths that already hold the token in memory — secrets-manager fetches, per-request injection, per-user lookup, etc.

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["gmail", "slack"],
    credentials={
        "gmail": "ya29.your-access-token",
        "slack": "xoxb-your-bot-token",
    },
)
```

The token never touches the process environment. The dict is consulted first; env vars are only checked as fallback.

### 2. Environment Variables

Set credentials as environment variables. The `EnvironmentKeyStore` reads them automatically using the naming convention `TC_{CONNECTOR}_{CREDENTIAL_TYPE}`.

```bash
export TC_GMAIL_CREDENTIALS="ya29.your-access-token"
export TC_SLACK_CREDENTIALS="xoxb-your-bot-token"
```

```python
from toolsconnector.serve import ToolKit

# Credentials are read from environment variables automatically
kit = ToolKit(["gmail", "slack"])
```

This is the recommended approach for local development, CI/CD pipelines, twelve-factor apps, and any deployment with a single set of credentials per process.

### Resolution priority

Every connector follows the same resolution order (first match wins):

1. Programmatic `credentials` dict passed to `ToolKit`
2. `TC_{CONNECTOR}_CREDENTIALS` env var
3. `TC_{CONNECTOR}_API_KEY` env var
4. `TC_{CONNECTOR}_TOKEN` env var

If none resolve, `MissingConfigError` is raised with an actionable suggestion listing all four sources. Implementation: [`src/toolsconnector/serve/_credentials.py`](../../src/toolsconnector/serve/_credentials.py).

### 3. KeyStore

Use a `KeyStore` implementation for programmatic credential management with features like TTL-based expiry.

```python
from toolsconnector.serve import ToolKit
from toolsconnector.keystore import InMemoryKeyStore

store = InMemoryKeyStore()

# Pre-populate the store
import asyncio
asyncio.run(store.set("gmail:default:access_token", "ya29.token", ttl=3600))
asyncio.run(store.set("slack:default:bot_token", "xoxb-token"))

kit = ToolKit(["gmail", "slack"], keystore=store)
```

Built-in KeyStore implementations:

| KeyStore | Use Case | Persistence |
|----------|----------|-------------|
| `InMemoryKeyStore` | Development, testing, short-lived processes | None (lost on exit) |
| `EnvironmentKeyStore` | Production, CI/CD, twelve-factor apps | Read-only from env |

The `KeyStore` protocol is simple -- any class with async `get()`, `set()`, `delete()`, and `exists()` methods satisfies it. You can implement your own backed by Redis, Vault, a database, or any other storage.

## OAuth2 Token Refresh

For connectors that use OAuth2 (Gmail, Google Drive, Google Calendar), ToolsConnector handles token refresh automatically:

1. Before each request, the `OAuth2Provider` checks if the access token is expired or about to expire (within a 60-second buffer).
2. If refresh is needed and a refresh token is available, it exchanges the refresh token for a new access token at the provider's token endpoint.
3. The new tokens are persisted to the configured `KeyStore`.
4. If no refresh token is available and the access token is expired, a `TokenExpiredError` is raised.

You provide the initial tokens; the library keeps them alive.

## Multiple instances of the same tool

A single `ToolKit` holds one credential per connector name. To use the same tool with **different tokens in the same process** — e.g. a workspace-A Notion token and a workspace-B Notion token, or two Slack workspaces — you have three options. All are equally valid primitives; pick whichever fits your code shape.

### Option A — Multiple ToolKits, one per credential

The simplest pattern. Each ToolKit is an independent unit of configuration: connectors, credentials, circuit-breaker state, rate-limit windows are all isolated.

```python
from toolsconnector.serve import ToolKit

workspace_a = ToolKit(["notion"], credentials={"notion": "ntn_workspace_a_token"})
workspace_b = ToolKit(["notion"], credentials={"notion": "ntn_workspace_b_token"})

# Same action name, different credentials → different workspaces
a_pages = workspace_a.execute("notion_search", {"query": "OKR"})
b_pages = workspace_b.execute("notion_search", {"query": "OKR"})
```

This composes naturally with whatever lifecycle your app already has — request handlers, background jobs, per-user contexts. Hold a ToolKit per credential and discard it when the credential rotates.

### Option B — Direct connector instantiation

Skip ToolKit entirely when you don't need its discovery / serving / OpenAI-schema features. Every connector class accepts `credentials=...` directly:

```python
from toolsconnector.connectors.notion import Notion

a = Notion(credentials="ntn_workspace_a_token")
b = Notion(credentials="ntn_workspace_b_token")

# Use the async methods directly
import asyncio
pages_a = asyncio.run(a.asearch(query="OKR"))
pages_b = asyncio.run(b.asearch(query="OKR"))
```

Best for library code that already has an event loop, or when you want a long-lived connector instance pinned to one credential.

### Option C — Reuse a ToolKit, rebuild on credential change

If a single execution flow needs to switch credentials briefly, instantiate a fresh ToolKit at that point. ToolKits are cheap; there's no shared global state preventing this.

```python
def run_for_workspace(token: str, action: str, args: dict) -> dict:
    kit = ToolKit(["notion"], credentials={"notion": token})
    return json.loads(kit.execute(action, args))
```

## Isolated configuration (ToolKitFactory)

When the same connector configuration (which tools, which middleware, which circuit-breaker settings) is reused across many credential sets, `ToolKitFactory` lets you declare the shared shape once and stamp out independent ToolKit instances per credential set:

```python
from toolsconnector.serve import ToolKitFactory

# Shared config — no credentials held at this layer
factory = ToolKitFactory(
    connectors=["gmail", "slack"],
    exclude_dangerous=True,
)

# Stamp out independent ToolKits — caller decides what each one is for
kit_one = factory.for_tenant(
    tenant_id="config-a",  # arbitrary string — just an identity label
    credentials={"gmail": "token-a", "slack": "token-a"},
)
kit_two = factory.for_tenant(
    tenant_id="config-b",
    credentials={"gmail": "token-b", "slack": "token-b"},
)
```

The `tenant_id` parameter is a label for telemetry / debugging — it does NOT encode a tenancy model. ToolsConnector does not know or care whether the label maps to a user, an organization, a workspace, a CI run, or something else. That mapping lives in your application code.

Each `for_tenant()` call yields an isolated ToolKit with its own credential set, circuit-breaker state, and rate-limit windows — exactly equivalent to constructing the ToolKit directly. The factory just removes the boilerplate of repeating the shared config.

## Security Best Practices

- Never commit credentials to version control. Use environment variables or a secrets manager.
- Use short-lived access tokens with refresh tokens where possible.
- Scope credentials to the minimum permissions each connector needs.
- Rotate API keys regularly. The `KeyStore` TTL feature helps enforce expiry.
- For production, implement a `KeyStore` backed by a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.) rather than using `InMemoryKeyStore`.
- If your application holds credentials for many independent contexts, isolate each context to its own `ToolKit` instance (see "Multiple instances of the same tool" above). Do not share a `ToolKit` across credential boundaries.
