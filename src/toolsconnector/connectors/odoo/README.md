# Odoo

> Odoo (formerly OpenERP) — read & write any Odoo model (contacts, sales orders, invoices, inventory, HR, eCommerce, POS, Helpdesk, …) through its ORM over JSON-RPC. BYOK: instance url + db + username + API key.

| | |
|---|---|
| **Company** | Odoo S.A. |
| **Category** | CRM & Support (ERP) |
| **Protocol** | JSON-RPC |
| **Base URL** | per-instance (your Odoo url, e.g. `https://yourcompany.odoo.com`) |
| **Website** | [odoo.com](https://www.odoo.com) |
| **API Docs** | [External API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html) |
| **Auth** | API Key (BYOK: url+db+username+api_key) |
| **Rate Limit** | instance-dependent |
| **Pricing** | Open-source (Community) / Odoo Online plans |
| **Verification** | ✅ Tier 1 — Live verified (2026-06-19, real Odoo 19.3 instance across ~27 apps / ~50 models) |

---

## Overview

Odoo (formerly OpenERP) is a full ERP — CRM, Sales, Inventory, Accounting, HR, eCommerce, POS, Helpdesk, Manufacturing, Projects, and more — and it exposes its **entire** ORM over a single JSON-RPC endpoint. Every business object is reached through the same handful of ORM methods, so this connector gives you the full power of Odoo (including its domain filter language and `read_group` aggregation) through one consistent interface, instead of a curated, lossy subset.

This is the **first JSON-RPC connector** in the catalog. It was live-verified on **2026-06-19** against a real **Odoo 19.3** instance across **~27 apps / ~50 models**. BYOK: provide your instance url, database, username, and API key — the connector performs only the protocol exchange and never stores tokens.

## Use Cases

- Sync CRM contacts and leads (`res.partner`, `crm.lead`) into and out of Odoo
- Create and confirm sales orders and post customer invoices (`sale.order`, `account.move`)
- Query inventory levels and product catalogs across warehouses
- Pull HR, eCommerce, POS, and Helpdesk records for analytics and reporting
- Let an AI agent discover any model's schema at runtime (`fields_get`) and read/write it generically

## Installation

```bash
pip install "toolsconnector[odoo]"
```

### Credentials — Odoo needs **four** values, not one

> ⚠️ **Heads-up — Odoo is different from almost every other connector.** Most ToolsConnector connectors authenticate with a **single** API key or token *string*. **Odoo needs four values**, supplied **together as one JSON object** (a Python `dict`, or a JSON-encoded string) — never a bare string.

| Field | What it is | Where to find it |
|---|---|---|
| `url` | Your Odoo instance URL | the address you sign in at — e.g. `https://yourcompany.odoo.com` |
| `db` | The database name | usually your subdomain; it's in the database selector on the login screen |
| `username` | Your login | the email/login you sign in with — e.g. `you@example.com` |
| `api_key` | A per-user API key | **Preferences → Account Security → New API Key** (Odoo 14+). `password` is accepted as an alias only if 2FA is off. |

```json
{
  "url": "https://yourcompany.odoo.com",
  "db": "yourcompany",
  "username": "you@example.com",
  "api_key": "<API key from Preferences → Account Security>"
}
```

In Python you pass that object as a **`dict`**. For the `TC_ODOO_CREDENTIALS` environment variable you pass it as a **JSON-encoded string** (it carries four fields, not one):

```bash
export TC_ODOO_CREDENTIALS='{"url":"https://yourcompany.odoo.com","db":"yourcompany","username":"you@example.com","api_key":"..."}'
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["odoo"], credentials={"odoo": {
    "url": "https://yourcompany.odoo.com",
    "db": "yourcompany",
    "username": "you@example.com",
    "api_key": "your-api-key",
}})

# Read customers (partners with a positive customer_rank)
result = kit.execute("odoo_search_read", {
    "model": "res.partner",
    "domain": [["customer_rank", ">", 0]],
    "fields": ["name", "email"],
    "limit": 50,
})
print(result)

# Create a new contact
new_id = kit.execute("odoo_create", {
    "model": "res.partner",
    "values": {"name": "Acme Corp", "email": "hello@acme.example"},
})
print(new_id)
```

### MCP Server

```python
kit = ToolKit(["odoo"], credentials={"odoo": {
    "url": "https://yourcompany.odoo.com",
    "db": "yourcompany",
    "username": "you@example.com",
    "api_key": "your-api-key",
}})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["odoo"], credentials={"odoo": {
    "url": "https://yourcompany.odoo.com", "db": "yourcompany",
    "username": "you@example.com", "api_key": "your-api-key",
}})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Sign in to your Odoo instance and open **Preferences → Account Security**
2. Under **API Keys**, generate a new key and copy the value (Odoo 14+ issues per-user API keys)
3. Provide it as the `api_key` alongside your instance `url`, `db`, and `username`

With two-factor authentication enabled, an API key is **required** — a login password will not authenticate over the external API.

[Get credentials →](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("odoo_search_read", {"model": "res.partner"})
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

- Call `fields_get` to discover a model's fields (names, types, labels) at runtime before reading or writing — essential when a custom module has added fields you don't know about
- Filters use Odoo's **domain** language: a list of `[field, operator, value]` triples, e.g. `[["customer_rank", ">", 0], ["country_id.code", "=", "US"]]`. Adjacent triples are implicitly ANDed; insert `"|"` / `"&"` / `"!"` prefix operators for OR/AND/NOT
- Use `call_method` for business actions that aren't plain CRUD — e.g. `action_confirm` on a `sale.order`, `action_post` on an `account.move`
- Use `read_group` for aggregation (counts, sums, averages grouped by a field) instead of pulling every record and aggregating client-side
- Every record is a plain `dict` (field name → value) — Odoo instances are schema-dynamic, so there are no fixed per-model types

## Related Connectors

- [HubSpot](../hubspot/) — CRM contacts, deals, and pipelines
- [Salesforce](../salesforce/) — CRM and sales cloud
- [Stripe](../stripe/) — Payments, invoicing, and billing

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
