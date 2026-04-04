# Credentials Guide

How credentials work in ToolsConnector.

## The BYOK Philosophy

ToolsConnector follows the Bring Your Own Key (BYOK) model. You register your own OAuth apps, get your own API keys, and choose how to store them. The library handles the protocol (token exchange, refresh, scope validation) but never manages or stores credentials on your behalf.

This design means zero liability for credential storage, full compatibility with enterprise security policies, and no dependency on any hosted service.

## Three Ways to Provide Credentials

### 1. Programmatic (Inline)

Pass credentials directly when creating a `ToolKit`. Best for scripts, notebooks, and development.

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

This is the recommended approach for production deployments, CI/CD pipelines, and twelve-factor apps.

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

## Multi-Tenant Credentials (ToolKitFactory)

For SaaS applications serving multiple users, use `ToolKitFactory` to create per-tenant `ToolKit` instances:

```python
from toolsconnector.serve import ToolKitFactory

factory = ToolKitFactory(
    connectors=["gmail", "slack"],
    keystore=my_keystore,
)

# Create a ToolKit for a specific tenant
kit = factory.for_tenant(
    tenant_id="user-123",
    credentials={
        "gmail": user_gmail_token,
        "slack": user_slack_token,
    },
)

result = kit.execute("gmail_list_emails", {"query": "is:unread"})
```

Each tenant gets isolated credentials, rate limits, and circuit breaker state.

## Security Best Practices

- Never commit credentials to version control. Use environment variables or a secrets manager.
- Use short-lived access tokens with refresh tokens where possible.
- Scope credentials to the minimum permissions each connector needs.
- In multi-tenant deployments, use separate `KeyStore` namespaces per tenant.
- Rotate API keys regularly. The `KeyStore` TTL feature helps enforce expiry.
- For production, implement a `KeyStore` backed by a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.) rather than using `InMemoryKeyStore`.
