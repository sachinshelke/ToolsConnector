# Stripe

> Payment processing, subscriptions, and billing

| | |
|---|---|
| **Company** | Stripe Inc. |
| **Category** | Finance |
| **Protocol** | REST |
| **Website** | [stripe.com](https://stripe.com) |
| **API Docs** | [docs.stripe.com](https://docs.stripe.com/api) |
| **Auth** | API Key (Secret Key) |
| **Rate Limit** | 100 read/sec, 100 write/sec |
| **Pricing** | 2.9% + 30c per transaction |
| **Verification** | ✅ Tier 1 — Live verified (38/40 happy-path + 2/40 envelope-verified, 2026-06-13, test mode) |

---

## Overview

The Stripe API provides a complete payment infrastructure. Process payments, manage subscriptions, handle invoices, issue refunds, and build checkout experiences. Supports cards, bank transfers, and 100+ payment methods worldwide.

## Verification Status

> **Tier 1 — Live verified (2026-06-13, Stripe test mode, via `ToolKit.aexecute` — the serve/MCP path): 38/40 actions happy-path + 2/40 envelope-verified. Zero transport bugs found.**
>
> - **Happy-path (38):** full customer lifecycle (create → get → update → delete, including the HTTP-200 `deleted: true` tombstone on post-delete reads), products/prices (one-time + recurring), the complete PaymentIntent lifecycle (create with pinned `payment_method_types` → confirm with `return_url` → auto- and manual-capture → cancel), charges + a real partial refund, a **real dispute lifecycle** (created via Stripe's `pm_card_createDispute` test card → fetched → closed), subscriptions (trial → cancel-at-period-end → immediate cancel), invoices (finalized `send_invoice` invoice fetched → voided), Checkout Sessions, SetupIntents, events, balance, and every list endpoint with real data.
> - **Envelope-verified (2):** `create_payout` — Stripe accepted the request and returned its account-config constraint as a clean typed `ValidationError` ("you don't have any external accounts in that currency"); payouts require a bank account configured in the Dashboard. `get_payout` — bogus-ID probe returned a clean typed `NotFoundError`.
> - The live sweep drove three connector improvements, then re-verified them: `payment_method_types`/`payment_method`/`capture_method` on `create_payment_intent`, `return_url` on `confirm_payment_intent`, and `latest_charge` + customer `deleted` surfaced in the response types.

## Use Cases

- Payment processing
- Subscription management
- Invoice generation
- Marketplace payments
- Revenue analytics

## Installation

```bash
pip install "toolsconnector[stripe]"
```

Set your credentials:

```bash
export TC_STRIPE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["stripe"], credentials={"stripe": "your-token"})

# List events from your Stripe account
result = kit.execute("stripe_list_events", {"type": "your-type", "limit": 10})
print(result)
```

### MCP Server

```python
kit = ToolKit(["stripe"], credentials={"stripe": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["stripe"], credentials={"stripe": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key (Secret Key)

1. Dashboard
2. Developers
3. API Keys

[Get credentials &rarr;](https://dashboard.stripe.com/apikeys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("stripe_list_events", {})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
```

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Rate limit is 100 read/sec, 100 write/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`cancel_subscription`, `capture_payment_intent`, `close_dispute`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses
- This connector has 40 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs
- **Server-side confirmation:** pin `payment_method_types=["card"]` when creating a PaymentIntent you'll confirm server-side, or pass `return_url` to `confirm_payment_intent` — unpinned intents inherit the Dashboard's payment methods, which include redirect-based ones that make Stripe reject a confirm without a `return_url` (HTTP 400, verified live)
- **Refund flows:** a confirmed PaymentIntent's `latest_charge` is the charge ID to pass to `refund_charge`
- **Deleted customers:** Stripe answers `get_customer` on a deleted customer with HTTP 200 and `deleted: true` (not a 404) — check the `deleted` field
- **Manual capture:** create the intent with `capture_method="manual"`, confirm it, then `capture_payment_intent` when ready (auth-then-capture)
- Develop against test mode (`sk_test_…` keys) with [Stripe's test cards](https://docs.stripe.com/testing) — e.g. `pm_card_visa`, `tok_bypassPending`, `pm_card_createDispute`

## Related Connectors

- [Plaid](../plaid/) — Banking data

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
