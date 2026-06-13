"""Declarative bindings for the 3 hardest connectors — authored by hand here,
but in production these would be *extracted* from the connector (Python remains
the source of truth) or authored as YAML once and generate ALL languages.

Each binding below was transcribed directly from the imperative connector code.
Together the 9 actions exercise every "hard 20%" pattern the survey found:

  - indexed query params        Airtable  fields[i]=
  - indexed-object query params Airtable  sort[i][field]=, sort[i][direction]=
  - bracket/batch query params  Airtable  records[]=  (DELETE)
  - JSON body key placement     Airtable  {"fields": ...}
  - per-item body wrapping      Airtable  {"records": [{"fields": r}, ...]}
  - multiple base URLs          Airtable  data vs meta;  Twilio  main vs verify
  - path templating from creds  Twilio    /Accounts/{account_sid}/...
  - base-URL templating         Shopify   https://{store}.myshopify.com/...
  - form-encoded bodies         Twilio    To=&From=&Body=
  - single-key body wrapping    Shopify   {"product": {...}}
  - size clamping               pageSize<=100, PageSize<=1000, limit<=250
  - offset-token pagination     Airtable  offset
  - follow-URL pagination       Twilio    next_page_uri
  - link-header pagination      Shopify   Link: rel=next page_info
  - custom auth header          Shopify   X-Shopify-Access-Token
  - basic auth from split creds Twilio    base64(sid:token)
"""

from __future__ import annotations

from .binding_ir import (
    ActionBinding,
    AuthKind,
    ConnectorBinding,
    ContextVar,
    EndpointBinding,
    Location,
    PaginationBinding,
    PaginationKind,
    ParamBinding,
    Style,
)


def _p(name, wire, loc, **kw):
    return ParamBinding(name=name, wire=wire, location=loc, **kw)


# ---------------------------------------------------------------------------
# AIRTABLE
# ---------------------------------------------------------------------------
AIRTABLE = ConnectorBinding(
    name="airtable",
    default_endpoint="data",
    endpoints={
        "data": EndpointBinding(
            id="data", base_url="https://api.airtable.com/v0", encoding="json",
            auth_kind=AuthKind.BEARER, auth_header="Authorization",
        ),
        "meta": EndpointBinding(
            id="meta", base_url="https://api.airtable.com/v0/meta", encoding="json",
            auth_kind=AuthKind.BEARER, auth_header="Authorization",
        ),
    },
    actions={
        "list_records": ActionBinding(
            name="list_records", method="GET", endpoint="data",
            path="/{base_id}/{table_name}", unwrap="records",
            params=[
                _p("base_id", "base_id", Location.PATH),
                _p("table_name", "table_name", Location.PATH),
                _p("limit", "pageSize", Location.QUERY, style=Style.SIMPLE, max=100, default=100),
                _p("fields", "fields", Location.QUERY, style=Style.INDEXED),
                _p("filter_formula", "filterByFormula", Location.QUERY),
                _p("sort", "sort", Location.QUERY, style=Style.INDEXED_OBJECT,
                   subkeys=["field", "direction"],
                   subkey_defaults={"field": "", "direction": "asc"}),
                _p("offset", "offset", Location.QUERY),
            ],
            pagination=PaginationBinding(
                kind=PaginationKind.OFFSET_TOKEN, token_field="offset",
                token_param_py="offset", items_field="records",
            ),
        ),
        "delete_records": ActionBinding(
            name="delete_records", method="DELETE", endpoint="data",
            path="/{base_id}/{table_name}",
            params=[
                _p("base_id", "base_id", Location.PATH),
                _p("table_name", "table_name", Location.PATH),
                _p("record_ids", "records", Location.QUERY, style=Style.BRACKET, max_items=10),
            ],
        ),
        "create_record": ActionBinding(
            name="create_record", method="POST", endpoint="data",
            path="/{base_id}/{table_name}",
            params=[
                _p("base_id", "base_id", Location.PATH),
                _p("table_name", "table_name", Location.PATH),
                _p("fields", "fields", Location.BODY, body_key="fields", ty="object"),
            ],
        ),
        "batch_create": ActionBinding(
            name="batch_create", method="POST", endpoint="data",
            path="/{base_id}/{table_name}",
            params=[
                _p("base_id", "base_id", Location.PATH),
                _p("table_name", "table_name", Location.PATH),
                _p("records", "records", Location.BODY, body_key="records",
                   item_wrap="fields", max_items=10, ty="object[]"),
            ],
        ),
        "get_base_schema": ActionBinding(
            name="get_base_schema", method="GET", endpoint="meta",
            path="/bases/{base_id}/tables", unwrap="tables",
            params=[_p("base_id", "base_id", Location.PATH)],
        ),
    },
)


# ---------------------------------------------------------------------------
# TWILIO
# ---------------------------------------------------------------------------
TWILIO = ConnectorBinding(
    name="twilio",
    default_endpoint="main",
    ctx_vars=[ContextVar(name="account_sid", source="split:0::")],
    endpoints={
        "main": EndpointBinding(
            id="main", base_url="https://api.twilio.com/2010-04-01", encoding="form",
            auth_kind=AuthKind.BASIC_SPLIT, auth_header="Authorization",
        ),
        "verify": EndpointBinding(
            id="verify", base_url="https://verify.twilio.com/v2", encoding="form",
            auth_kind=AuthKind.BASIC_SPLIT, auth_header="Authorization",
        ),
    },
    actions={
        "send_sms": ActionBinding(
            name="send_sms", method="POST", endpoint="main",
            path="/Accounts/{account_sid}/Messages.json",
            params=[
                _p("to", "To", Location.BODY),
                _p("from_", "From", Location.BODY),
                _p("body", "Body", Location.BODY),
            ],
        ),
        "list_messages": ActionBinding(
            name="list_messages", method="GET", endpoint="main",
            path="/Accounts/{account_sid}/Messages.json", unwrap="messages",
            params=[
                _p("to", "To", Location.QUERY),
                _p("from_", "From", Location.QUERY),
                _p("limit", "PageSize", Location.QUERY, max=1000, default=20),
            ],
            pagination=PaginationBinding(
                kind=PaginationKind.FOLLOW_URL, token_field="next_page_uri",
                items_field="messages",
            ),
        ),
        "create_verify_service": ActionBinding(
            name="create_verify_service", method="POST", endpoint="verify",
            path="/Services",
            params=[_p("friendly_name", "FriendlyName", Location.BODY)],
        ),
    },
)


# ---------------------------------------------------------------------------
# SHOPIFY
# ---------------------------------------------------------------------------
SHOPIFY = ConnectorBinding(
    name="shopify",
    default_endpoint="main",
    ctx_vars=[
        ContextVar(name="access_token", source="split:0::"),
        ContextVar(name="store", source="split:1::"),
    ],
    endpoints={
        "main": EndpointBinding(
            id="main", base_url="https://{store}.myshopify.com/admin/api/2024-01",
            encoding="json", auth_kind=AuthKind.HEADER_KEY,
            auth_header="X-Shopify-Access-Token", auth_cred_ctx="access_token",
            extra_headers={"Accept": "application/json"},
        ),
    },
    actions={
        "list_products": ActionBinding(
            name="list_products", method="GET", endpoint="main",
            path="/products.json", unwrap="products",
            params=[
                _p("limit", "limit", Location.QUERY, max=250, default=50),
                _p("since_id", "since_id", Location.QUERY),
                _p("page_info", "page_info", Location.QUERY),  # absent on page 1
            ],
            pagination=PaginationBinding(
                kind=PaginationKind.LINK_HEADER, token_param_py="page_info",
                link_rel="next", carry=["limit"], items_field="products",
            ),
        ),
        "create_product": ActionBinding(
            name="create_product", method="PUT", endpoint="main",
            path="/products.json", body_wrap="product",
            params=[
                _p("title", "title", Location.BODY),
                _p("body_html", "body_html", Location.BODY),
                _p("vendor", "vendor", Location.BODY),
                _p("product_type", "product_type", Location.BODY),
                _p("variants", "variants", Location.BODY, ty="object[]"),
            ],
        ),
    },
)


# ---------------------------------------------------------------------------
# STRIPE  (Tier 1 — live-verified 2026-06-13). First Tier-1 connector bound;
# proves the binding pipeline on a connector we actually ship SDKs for.
# ---------------------------------------------------------------------------
STRIPE = ConnectorBinding(
    name="stripe",
    default_endpoint="main",
    endpoints={
        "main": EndpointBinding(
            id="main", base_url="https://api.stripe.com/v1", encoding="form",
            auth_kind=AuthKind.BASIC_USER, auth_header="Authorization",
        ),
    },
    actions={
        "list_customers": ActionBinding(
            name="list_customers", method="GET", endpoint="main",
            path="/customers", unwrap="data",
            params=[
                _p("limit", "limit", Location.QUERY, max=100, default=10),
                _p("starting_after", "starting_after", Location.QUERY),
            ],
        ),
        "get_customer": ActionBinding(
            name="get_customer", method="GET", endpoint="main",
            path="/customers/{customer_id}",
            params=[_p("customer_id", "customer_id", Location.PATH)],
        ),
        "create_customer": ActionBinding(
            name="create_customer", method="POST", endpoint="main",
            path="/customers",
            params=[
                _p("email", "email", Location.BODY),
                _p("name", "name", Location.BODY),
                _p("description", "description", Location.BODY),
            ],
        ),
    },
)


ALL = {"airtable": AIRTABLE, "twilio": TWILIO, "shopify": SHOPIFY, "stripe": STRIPE}
