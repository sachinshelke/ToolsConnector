# Resilience Guide

How ToolsConnector handles failures, retries, and degraded upstream services.

## Overview

External APIs fail. They return 429s, time out, rotate credentials, and go down entirely. ToolsConnector provides a layered resilience strategy so your application or AI agent stays operational even when individual connectors are degraded.

These features live in `ToolKit.execute()` / `aexecute()`, so they apply to MCP, REST and the CLI too. Calling a connector class directly (without a `ToolKit`) bypasses them.

## Circuit Breaker

The circuit breaker prevents cascading failures by temporarily disabling a connector after repeated failures.

**How it works:**

1. **Closed** (normal): Requests flow through. Failures are counted.
2. **Open** (tripped): After `circuit_breaker_threshold` consecutive failures, the circuit opens. All requests are immediately rejected with a `ServerError` -- no HTTP calls are made. This protects both your application and the upstream API.
3. **Half-open** (probing): After `circuit_breaker_recovery` seconds, one test request is allowed through. If it succeeds, the circuit closes. If it fails, it reopens.

**Configuration:**

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["gmail", "slack"],
    credentials={...},
    circuit_breaker_threshold=5,   # Open after 5 consecutive failures
    circuit_breaker_recovery=30,   # Try again after 30 seconds (default 60)
)
```

**Per-connector isolation:** Each connector has its own circuit breaker. A failing Gmail API does not affect Slack operations.

## Auto-Retry with Exponential Backoff

Transient failures (timeouts, 429s, 5xx) are retried automatically until the timeout budget runs out, as long as repeating the call is safe.

**How it works:**

1. The call fails with a retry-eligible error.
2. If the error carries a `Retry-After` value, wait that long. Otherwise wait 2, 4, 8… seconds.
3. Retry while there is budget left (`timeout_budget`, 25 seconds by default). There is no separate retry count.

> **Writes are not resent after a timeout, connection failure or 5xx.** The service may already have acted, so a retry could send a payment or message twice. Only actions declared `access="read"` or `idempotent=True` are retried for those errors. Any action is retried after a 429 or an expired token, because the service refused the call. A write that fails this way raises with `retry_eligible=False` and a suggestion to check before sending it again. Releases before 0.5.0 retried writes too.

**Which errors are retried:**

| Error | Retried | Reason |
|-------|---------|--------|
| `RateLimitError` | Yes | Transient, wait and retry |
| `TimeoutError` | Reads and `idempotent` actions only | The service may have acted before timing out |
| `ConnectionError` | Reads and `idempotent` actions only | The request may have reached the service |
| `ServerError` (5xx) | Reads and `idempotent` actions only | The service may have acted before failing |
| `NotFoundError` | No | Resource does not exist |
| `ValidationError` | No | Bad input, retrying won't help |
| `InvalidCredentialsError` | No | Credentials are wrong |
| `TokenExpiredError` | Once | The connector is rebuilt and the credential re-read, in case it was replaced |
| `MissingConfigError` | No | No credential is configured |

Each error carries a `retry_eligible` boolean that the retry loop checks.

## Timeout Budgets

Two limits apply to every call:

```python
kit = ToolKit(
    ["gmail"],
    credentials={...},
    action_timeout=15.0,   # One attempt (default 15 seconds)
    timeout_budget=25.0,   # The whole call, including retries (default 25 seconds)
)
```

When the budget runs out, the last error is raised; if every attempt timed out, that is `TimeoutError`.

## Expired Tokens

ToolsConnector does not refresh OAuth tokens for you. When a service rejects an expired token, the call is retried once with the credential re-read, then `TokenExpiredError` is raised. Refresh the token in your own code and build a new `ToolKit` with it:

```python
from toolsconnector.errors import TokenExpiredError

try:
    kit.execute("gmail_list_emails", {"query": "is:unread"})
except TokenExpiredError:
    ...  # refresh the token, then create a new ToolKit with it
```

An MCP server reads its credentials when it starts, so restart it after replacing a token.

## Pre-Validation

Inputs are checked before the HTTP request is made:

- Missing required parameters
- Wrong basic types (string instead of integer)
- Values outside an enum

A failed check raises `ValidationError` naming the parameter. Numeric ranges are left to the service. A parameter the action doesn't have raises `TypeError`.

## Graceful Degradation

One failing connector does not affect the others. `ToolKit` reports the last known state of each:

```python
kit.get_connector_status()
# {"gmail": "healthy", "slack": "degraded"}   # "unknown" until first used
```

## Structured Error Messages

Every error in ToolsConnector carries machine-readable metadata suitable for both human debugging and AI agent routing:

```python
from toolsconnector.errors import ToolsConnectorError

try:
    result = kit.execute("slack_send_message", {"channel": "#general", "text": "Hello"})
except ToolsConnectorError as e:
    print(e.code)                # "API_RATE_LIMITED"
    print(e.connector)           # "slack"
    print(e.action)              # "send_message"
    print(e.retry_eligible)      # True
    print(e.retry_after_seconds) # 30.0
    print(e.suggestion)          # "Wait 30 seconds and retry"
    print(e.to_dict())           # Full JSON-serializable dict
    print(e.to_json())           # Compact JSON string
```

## Dry Run Mode

Validate a call without executing it. Useful for testing agent workflows and auditing what an AI agent would do.

```python
kit = ToolKit(["slack"], credentials={...})

# This validates the input and returns what WOULD happen,
# but does not actually send the message.
result = kit.execute("slack_send_message", {
    "channel": "#general",
    "text": "This will not actually be sent",
}, dry_run=True)
```

`dry_run` is an argument of `execute()` / `aexecute()`. The arguments are validated first, so an invalid call raises `ValidationError`. Only actions declared `access="read"` execute; every other action, including one with no declared access, returns a preview.

## Incomplete Pages

`has_more` means another page exists. If a page says so but has no way to load it, `anext_page()`, `next_page()`, `collect()` and `collect_sync()` raise `PaginationNotWiredError` (`CONNECTOR_PAGINATION_NOT_WIRED`). Before 0.4.0 they stopped silently and returned partial results.

Actions that take a next-page URL (Outlook, Teams, GitHub, Docker Hub) accept it only on the service's own host, because the request carries your token. Any other host raises `ValidationError`.
