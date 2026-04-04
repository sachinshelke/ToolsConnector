# Resilience Guide

How ToolsConnector handles failures, retries, and degraded upstream services.

## Overview

External APIs fail. They return 429s, time out, rotate credentials, and go down entirely. ToolsConnector provides a layered resilience strategy so your application or AI agent stays operational even when individual connectors are degraded.

The resilience features are implemented as middleware in the runtime pipeline. They execute in order around every action call: Auth -> Retry -> Rate Limit -> Logging -> Action Handler.

## Circuit Breaker

The circuit breaker prevents cascading failures by temporarily disabling a connector after repeated failures.

**How it works:**

1. **Closed** (normal): Requests flow through. Failures are counted.
2. **Open** (tripped): After `failure_threshold` consecutive failures, the circuit opens. All requests are immediately rejected with a `ConnectorError` -- no HTTP calls are made. This protects both your application and the upstream API.
3. **Half-open** (probing): After `recovery_timeout` seconds, one test request is allowed through. If it succeeds, the circuit closes. If it fails, it reopens.

**Configuration:**

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["gmail", "slack"],
    credentials={...},
    circuit_breaker={
        "failure_threshold": 5,    # Open after 5 consecutive failures
        "recovery_timeout": 30,    # Try again after 30 seconds
    },
)
```

**Per-connector isolation:** Each connector has its own circuit breaker. A failing Gmail API does not affect Slack operations.

## Auto-Retry with Exponential Backoff

Transient failures (timeouts, 429s, 503s) are retried automatically with exponential backoff and jitter.

**How it works:**

1. The first call fails with a retry-eligible error.
2. Wait `base_delay * 2^(attempt-1)` seconds, plus random jitter.
3. Retry up to `max_retries` times.
4. If a `RateLimitError` includes a `Retry-After` header value, that value is used as the minimum delay.

**Configuration:**

```python
kit = ToolKit(
    ["slack"],
    credentials={...},
    retry={
        "max_retries": 3,       # Up to 3 retry attempts
        "base_delay": 1.0,      # Initial delay: 1 second
        "max_delay": 60.0,      # Cap delay at 60 seconds
    },
)
```

**Which errors are retried:**

| Error | Retried | Reason |
|-------|---------|--------|
| `RateLimitError` | Yes | Transient, wait and retry |
| `TimeoutError` | Yes | Network or server slowness |
| `ConnectionError` | Yes | Transient network issue |
| `ServerError` (5xx) | Yes | Upstream instability |
| `NotFoundError` | No | Resource does not exist |
| `ValidationError` | No | Bad input, retrying won't help |
| `AuthError` | No | Credentials are wrong |

Each error carries a `retry_eligible` boolean that the retry middleware checks.

## Timeout Budgets

Every action call has a timeout budget. If the upstream API does not respond within the budget, a `TimeoutError` is raised.

```python
# Global timeout (applies to all connectors)
kit = ToolKit(["gmail"], credentials={...}, timeout=30.0)

# Per-connector timeout (set in connector init)
# Connectors default to 30 seconds
```

Timeouts work together with retries: each retry attempt gets the full timeout budget. If you have `timeout=10` and `max_retries=3`, the worst-case wall time is ~40 seconds (10s * 3 retries + backoff delays).

## Token Auto-Refresh

For OAuth2 connectors (Gmail, Google Drive, Google Calendar), access tokens are refreshed automatically before they expire.

The `OAuth2Provider` checks token expiry before every request with a configurable buffer (default: 60 seconds). If the token is about to expire and a refresh token is available, it performs the token exchange transparently.

```python
# No code needed -- refresh happens automatically.
# If refresh fails, a RefreshFailedError is raised.
# If no refresh token exists, a TokenExpiredError is raised.
```

The refresh operation is thread-safe. Concurrent requests that detect an expiring token will not trigger duplicate refreshes.

## Pre-Validation

Action inputs are validated against the JSON Schema before the HTTP request is made. This catches common mistakes early:

- Missing required parameters
- Wrong parameter types (string instead of integer)
- Values outside allowed ranges

Pre-validation errors raise `ValidationError` with a descriptive message indicating which parameter failed and why.

## Graceful Degradation

When a connector's circuit breaker is open, `ToolKit` can report which connectors are healthy and which are degraded:

```python
status = kit.health_check()
# {
#     "gmail": {"healthy": True, "latency_ms": 45.2},
#     "slack": {"healthy": False, "message": "Circuit open: 5 consecutive failures"},
# }
```

AI agents can use this information to route requests to healthy connectors or inform the user that a service is temporarily unavailable.

## Structured Error Messages

Every error in ToolsConnector carries machine-readable metadata suitable for both human debugging and AI agent routing:

```python
from toolsconnector.errors import ToolsConnectorError

try:
    result = kit.execute("slack_send_message", {"channel": "#general", "text": "Hello"})
except ToolsConnectorError as e:
    print(e.code)                # "RATE_LIMITED"
    print(e.connector)           # "slack"
    print(e.action)              # "send_message"
    print(e.retry_eligible)      # True
    print(e.retry_after_seconds) # 30.0
    print(e.suggestion)          # "Wait 30 seconds and retry"
    print(e.to_dict())           # Full JSON-serializable dict
    print(e.to_json())           # Compact JSON string
```

## Dry Run Mode

Validate destructive actions without executing them. Useful for testing agent workflows and auditing what an AI agent would do.

```python
kit = ToolKit(["slack"], credentials={...}, dry_run=True)

# This validates the input and returns what WOULD happen,
# but does not actually send the message.
result = kit.execute("slack_send_message", {
    "channel": "#general",
    "text": "This will not actually be sent",
})
```

In dry-run mode, actions marked `dangerous=True` return a preview of the operation instead of executing it. Read-only actions (`idempotent=True`) execute normally.
