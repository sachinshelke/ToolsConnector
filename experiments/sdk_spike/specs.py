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
    PathVariant,
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
# STRIPE  (Tier 1 — live-verified 2026-06-13). 39 of 40 actions bound
# declaratively; cancel_subscription is the documented escape hatch (its HTTP
# method switches POST↔DELETE on an arg value — the coverage classifier flagged
# it). All form-encoded; key-as-username Basic auth; cursor pagination via
# starting_after (a query param, modelled per-list). `metadata` (dynamic-key
# dict) is intentionally omitted — that's a separate vocab item, not bound here.
# ---------------------------------------------------------------------------
def _list(name, *extra_filters):
    """A standard Stripe list action: GET /{name}?limit&starting_after[&filters],
    with cursor pagination (next starting_after = id of the last item, while has_more)."""
    return ActionBinding(
        name=f"list_{name}", method="GET", endpoint="main",
        path=f"/{name}", unwrap="data",
        params=[
            *extra_filters,
            _p("limit", "limit", Location.QUERY, max=100, default=10),
            _p("starting_after", "starting_after", Location.QUERY),
        ],
        pagination=PaginationBinding(
            kind=PaginationKind.LAST_ID, items_field="data", token_param_py="starting_after",
        ),
    )


_META = _p("metadata", "metadata", Location.BODY, style=Style.MAP)  # metadata[k]=v


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
        # ---- Customers ----
        "list_customers": _list("customers"),
        "get_customer": ActionBinding(
            name="get_customer", method="GET", endpoint="main",
            path="/customers/{customer_id}",
            params=[_p("customer_id", "customer_id", Location.PATH)],
        ),
        "create_customer": ActionBinding(
            name="create_customer", method="POST", endpoint="main", path="/customers",
            params=[
                _p("email", "email", Location.BODY),
                _p("name", "name", Location.BODY),
                _p("description", "description", Location.BODY),
                _META,
            ],
        ),
        "update_customer": ActionBinding(
            name="update_customer", method="POST", endpoint="main",
            path="/customers/{customer_id}",
            params=[
                _p("customer_id", "customer_id", Location.PATH),
                _p("email", "email", Location.BODY),
                _p("name", "name", Location.BODY),
                _p("description", "description", Location.BODY),
                _META,
            ],
        ),
        "delete_customer": ActionBinding(
            name="delete_customer", method="DELETE", endpoint="main",
            path="/customers/{customer_id}",
            params=[_p("customer_id", "customer_id", Location.PATH)],
        ),
        # ---- Charges ----
        "list_charges": _list("charges", _p("customer", "customer", Location.QUERY)),
        "get_charge": ActionBinding(
            name="get_charge", method="GET", endpoint="main",
            path="/charges/{charge_id}",
            params=[_p("charge_id", "charge_id", Location.PATH)],
        ),
        "create_charge": ActionBinding(
            name="create_charge", method="POST", endpoint="main", path="/charges",
            params=[
                _p("amount", "amount", Location.BODY),
                _p("currency", "currency", Location.BODY),
                _p("customer", "customer", Location.BODY),
                _p("source", "source", Location.BODY),
                _p("description", "description", Location.BODY),
                _META,
            ],
        ),
        # ---- Refunds ----
        "refund_charge": ActionBinding(
            name="refund_charge", method="POST", endpoint="main", path="/refunds",
            params=[
                _p("charge_id", "charge", Location.BODY),
                _p("amount", "amount", Location.BODY),
                _p("reason", "reason", Location.BODY),
            ],
        ),
        "list_refunds": _list("refunds", _p("charge", "charge", Location.QUERY)),
        # ---- PaymentIntents ----
        "create_payment_intent": ActionBinding(
            name="create_payment_intent", method="POST", endpoint="main",
            path="/payment_intents",
            params=[
                _p("amount", "amount", Location.BODY),
                _p("currency", "currency", Location.BODY),
                _p("customer", "customer", Location.BODY),
                _p("description", "description", Location.BODY),
                _p("payment_method_types", "payment_method_types", Location.BODY,
                   style=Style.INDEXED),
                _p("payment_method", "payment_method", Location.BODY),
                _p("capture_method", "capture_method", Location.BODY),
            ],
        ),
        "get_payment_intent": ActionBinding(
            name="get_payment_intent", method="GET", endpoint="main",
            path="/payment_intents/{payment_intent_id}",
            params=[_p("payment_intent_id", "payment_intent_id", Location.PATH)],
        ),
        "list_payment_intents": _list(
            "payment_intents", _p("customer", "customer", Location.QUERY)),
        "confirm_payment_intent": ActionBinding(
            name="confirm_payment_intent", method="POST", endpoint="main",
            path="/payment_intents/{payment_intent_id}/confirm",
            params=[
                _p("payment_intent_id", "payment_intent_id", Location.PATH),
                _p("payment_method", "payment_method", Location.BODY),
                _p("return_url", "return_url", Location.BODY),
            ],
        ),
        "cancel_payment_intent": ActionBinding(
            name="cancel_payment_intent", method="POST", endpoint="main",
            path="/payment_intents/{payment_intent_id}/cancel",
            params=[_p("payment_intent_id", "payment_intent_id", Location.PATH)],
        ),
        "capture_payment_intent": ActionBinding(
            name="capture_payment_intent", method="POST", endpoint="main",
            path="/payment_intents/{payment_intent_id}/capture",
            params=[
                _p("payment_intent_id", "payment_intent_id", Location.PATH),
                _p("amount_to_capture", "amount_to_capture", Location.BODY),
            ],
        ),
        # ---- Invoices ----
        "list_invoices": _list("invoices", _p("customer", "customer", Location.QUERY)),
        "get_invoice": ActionBinding(
            name="get_invoice", method="GET", endpoint="main",
            path="/invoices/{invoice_id}",
            params=[_p("invoice_id", "invoice_id", Location.PATH)],
        ),
        "void_invoice": ActionBinding(
            name="void_invoice", method="POST", endpoint="main",
            path="/invoices/{invoice_id}/void",
            params=[_p("invoice_id", "invoice_id", Location.PATH)],
        ),
        # ---- Balance ----
        "get_balance": ActionBinding(
            name="get_balance", method="GET", endpoint="main", path="/balance",
        ),
        # ---- Subscriptions (cancel_subscription = escape hatch, not bound) ----
        "create_subscription": ActionBinding(
            name="create_subscription", method="POST", endpoint="main",
            path="/subscriptions",
            params=[
                _p("customer", "customer", Location.BODY),
                _p("price", "items[0][price]", Location.BODY),
                _p("trial_days", "trial_period_days", Location.BODY),
            ],
        ),
        "list_subscriptions": _list(
            "subscriptions",
            _p("customer", "customer", Location.QUERY),
            _p("status", "status", Location.QUERY)),
        "get_subscription": ActionBinding(
            name="get_subscription", method="GET", endpoint="main",
            path="/subscriptions/{subscription_id}",
            params=[_p("subscription_id", "subscription_id", Location.PATH)],
        ),
        # ---- Products ----
        "create_product": ActionBinding(
            name="create_product", method="POST", endpoint="main", path="/products",
            params=[
                _p("name", "name", Location.BODY),
                _p("description", "description", Location.BODY),
                _META,
            ],
        ),
        "list_products": _list("products"),
        # ---- Prices ----
        "create_price": ActionBinding(
            name="create_price", method="POST", endpoint="main", path="/prices",
            params=[
                _p("product", "product", Location.BODY),
                _p("unit_amount", "unit_amount", Location.BODY),
                _p("currency", "currency", Location.BODY),
                _p("recurring_interval", "recurring[interval]", Location.BODY),
            ],
        ),
        "list_prices": _list("prices", _p("product", "product", Location.QUERY)),
        # ---- Checkout Sessions ----
        "create_checkout_session": ActionBinding(
            name="create_checkout_session", method="POST", endpoint="main",
            path="/checkout/sessions",
            params=[
                _p("mode", "mode", Location.BODY),
                _p("success_url", "success_url", Location.BODY),
                _p("cancel_url", "cancel_url", Location.BODY),
                _p("line_items", "line_items", Location.BODY, style=Style.INDEXED_OBJECT,
                   subkeys=["price", "quantity"], subkey_defaults={"quantity": 1}),
            ],
        ),
        # ---- Payment Methods ----
        "list_payment_methods": ActionBinding(
            name="list_payment_methods", method="GET", endpoint="main",
            path="/payment_methods", unwrap="data",
            params=[
                _p("customer", "customer", Location.QUERY),
                _p("type", "type", Location.QUERY),
                _p("limit", "limit", Location.QUERY, max=100, default=10),
                _p("starting_after", "starting_after", Location.QUERY),
            ],
            pagination=PaginationBinding(
                kind=PaginationKind.LAST_ID, items_field="data", token_param_py="starting_after",
            ),
        ),
        # ---- Disputes ----
        "list_disputes": _list("disputes"),
        "get_dispute": ActionBinding(
            name="get_dispute", method="GET", endpoint="main",
            path="/disputes/{dispute_id}",
            params=[_p("dispute_id", "dispute_id", Location.PATH)],
        ),
        "close_dispute": ActionBinding(
            name="close_dispute", method="POST", endpoint="main",
            path="/disputes/{dispute_id}/close",
            params=[_p("dispute_id", "dispute_id", Location.PATH)],
        ),
        # ---- Payouts ----
        "list_payouts": _list("payouts"),
        "create_payout": ActionBinding(
            name="create_payout", method="POST", endpoint="main", path="/payouts",
            params=[
                _p("amount", "amount", Location.BODY),
                _p("currency", "currency", Location.BODY),
            ],
        ),
        "get_payout": ActionBinding(
            name="get_payout", method="GET", endpoint="main",
            path="/payouts/{payout_id}",
            params=[_p("payout_id", "payout_id", Location.PATH)],
        ),
        # ---- Events ----
        "list_events": _list("events", _p("type", "type", Location.QUERY)),
        "get_event": ActionBinding(
            name="get_event", method="GET", endpoint="main",
            path="/events/{event_id}",
            params=[_p("event_id", "event_id", Location.PATH)],
        ),
        # ---- SetupIntents ----
        "create_setup_intent": ActionBinding(
            name="create_setup_intent", method="POST", endpoint="main",
            path="/setup_intents",
            params=[
                _p("customer", "customer", Location.BODY),
                _p("payment_method_types", "payment_method_types", Location.BODY,
                   style=Style.INDEXED),
            ],
        ),
        "get_setup_intent": ActionBinding(
            name="get_setup_intent", method="GET", endpoint="main",
            path="/setup_intents/{setup_intent_id}",
            params=[_p("setup_intent_id", "setup_intent_id", Location.PATH)],
        ),
    },
    # cancel_subscription: HTTP method switches POST (cancel_at_period_end) <->
    # DELETE (immediate) on an arg — generated as a typed method delegating to a
    # per-language override, so the SDK surface includes all 40 actions.
    escape_hatches=["cancel_subscription"],
)


# ---------------------------------------------------------------------------
# GITHUB — REST, Bearer auth, Link-header (follow-url) pagination.
# 37 actions: 36 declarative + 1 escape hatch (create_gist transforms its
# files map per-value: {name: {"content": v}} — imperative, not declarative).
# Exercises NEW patterns: conditional path_variants (list_repos 3-way,
# create_repo, list_workflow_runs) and LINK_FOLLOW pagination (GET the rel=next
# URL from the Link header directly).
# ---------------------------------------------------------------------------

def _gq(name, wire=None, **kw):  # query param
    return _p(name, wire or name, Location.QUERY, **kw)


def _gb(name, wire=None, **kw):  # JSON body param
    return _p(name, wire or name, Location.BODY, **kw)


def _gpath(name):  # path param
    return _p(name, name, Location.PATH)


def _glimit():  # limit -> per_page=min(limit,100), always sent
    return _p("limit", "per_page", Location.QUERY, max=100, default=30)


def _gpg(items=None):  # GitHub Link-header follow-url pagination
    return PaginationBinding(kind=PaginationKind.LINK_FOLLOW, link_rel="next", items_field=items)


def _ga(name, method, path, params=None, path_variants=None, unwrap=None, pagination=None):
    return ActionBinding(
        name=name, method=method, endpoint="main", path=path,
        params=params or [], path_variants=path_variants or [],
        unwrap=unwrap, pagination=pagination or PaginationBinding(),
    )


_OR = lambda: [_gpath("owner"), _gpath("repo")]  # noqa: E731 — common owner/repo path pair

_GH = [
    # Repositories
    _ga("list_repos", "GET", "/user/repos",
        params=[_gpath("org"), _gpath("user"), _glimit()],
        path_variants=[PathVariant(when_present="org", path="/orgs/{org}/repos"),
                       PathVariant(when_present="user", path="/users/{user}/repos")],
        pagination=_gpg()),
    _ga("get_repo", "GET", "/repos/{owner}/{repo}", params=_OR()),
    _ga("create_repo", "POST", "/user/repos",
        params=[_gpath("org"), _gb("name", required=True), _gb("private", default=False),
                _gb("auto_init", default=False), _gb("description")],
        path_variants=[PathVariant(when_present="org", path="/orgs/{org}/repos")]),
    _ga("fork_repo", "POST", "/repos/{owner}/{repo}/forks",
        params=[*_OR(), _gb("organization")]),
    # Issues
    _ga("list_issues", "GET", "/repos/{owner}/{repo}/issues",
        params=[*_OR(), _gq("state"), _gq("labels"), _gq("assignee"), _glimit()],
        pagination=_gpg()),
    _ga("create_issue", "POST", "/repos/{owner}/{repo}/issues",
        params=[*_OR(), _gb("title", required=True), _gb("body"),
                _gb("labels", ty="string[]"), _gb("assignees", ty="string[]")]),
    _ga("get_issue", "GET", "/repos/{owner}/{repo}/issues/{issue_number}",
        params=[*_OR(), _gpath("issue_number")]),
    _ga("update_issue", "PATCH", "/repos/{owner}/{repo}/issues/{issue_number}",
        params=[*_OR(), _gpath("issue_number"), _gb("title"), _gb("body"), _gb("state"),
                _gb("labels", ty="string[]"), _gb("assignees", ty="string[]")]),
    _ga("add_labels", "POST", "/repos/{owner}/{repo}/issues/{issue_number}/labels",
        params=[*_OR(), _gpath("issue_number"), _gb("labels", ty="string[]", required=True)]),
    _ga("remove_label", "DELETE", "/repos/{owner}/{repo}/issues/{issue_number}/labels/{label_name}",
        params=[*_OR(), _gpath("issue_number"), _gpath("label_name")]),
    _ga("create_comment", "POST", "/repos/{owner}/{repo}/issues/{issue_number}/comments",
        params=[*_OR(), _gpath("issue_number"), _gb("body", required=True)]),
    _ga("list_comments", "GET", "/repos/{owner}/{repo}/issues/{issue_number}/comments",
        params=[*_OR(), _gpath("issue_number"), _glimit()], pagination=_gpg()),
    # Pull requests
    _ga("list_pull_requests", "GET", "/repos/{owner}/{repo}/pulls",
        params=[*_OR(), _gq("state"), _glimit()], pagination=_gpg()),
    _ga("get_pull_request", "GET", "/repos/{owner}/{repo}/pulls/{pr_number}",
        params=[*_OR(), _gpath("pr_number")]),
    _ga("create_pull_request", "POST", "/repos/{owner}/{repo}/pulls",
        params=[*_OR(), _gb("title", required=True), _gb("head", required=True),
                _gb("base", required=True), _gb("body"), _gb("draft", default=False)]),
    _ga("merge_pull_request", "PUT", "/repos/{owner}/{repo}/pulls/{pr_number}/merge",
        params=[*_OR(), _gpath("pr_number"), _gb("merge_method", default="merge"),
                _gb("commit_title"), _gb("commit_message")]),
    # Commits / branches
    _ga("list_commits", "GET", "/repos/{owner}/{repo}/commits",
        params=[*_OR(), _gq("sha"), _gq("path"), _gq("author"), _glimit()], pagination=_gpg()),
    _ga("list_branches", "GET", "/repos/{owner}/{repo}/branches",
        params=[*_OR(), _glimit()], pagination=_gpg()),
    _ga("get_branch", "GET", "/repos/{owner}/{repo}/branches/{branch}",
        params=[*_OR(), _gpath("branch")]),
    # Releases
    _ga("list_releases", "GET", "/repos/{owner}/{repo}/releases",
        params=[*_OR(), _glimit()], pagination=_gpg()),
    _ga("get_latest_release", "GET", "/repos/{owner}/{repo}/releases/latest", params=_OR()),
    _ga("create_release", "POST", "/repos/{owner}/{repo}/releases",
        params=[*_OR(), _gb("tag_name", required=True), _gb("draft", default=False),
                _gb("prerelease", default=False), _gb("name"), _gb("body"),
                _gb("target_commitish")]),
    # Contents (note: {path} is interpolated raw in the connector, like our executor)
    _ga("get_content", "GET", "/repos/{owner}/{repo}/contents/{path}",
        params=[*_OR(), _gpath("path"), _gq("ref")]),
    _ga("create_or_update_file", "PUT", "/repos/{owner}/{repo}/contents/{path}",
        params=[*_OR(), _gpath("path"), _gb("message", required=True),
                _gb("content", required=True), _gb("sha"), _gb("branch")]),
    _ga("delete_file", "DELETE", "/repos/{owner}/{repo}/contents/{path}",
        params=[*_OR(), _gpath("path"), _gb("message", required=True),
                _gb("sha", required=True), _gb("branch")]),
    # Workflows
    _ga("list_workflows", "GET", "/repos/{owner}/{repo}/actions/workflows",
        params=[*_OR(), _glimit()], unwrap="workflows", pagination=_gpg("workflows")),
    _ga("list_workflow_runs", "GET", "/repos/{owner}/{repo}/actions/runs",
        params=[*_OR(), _gpath("workflow_id"), _gq("branch"), _gq("status"), _glimit()],
        path_variants=[PathVariant(when_present="workflow_id",
                                   path="/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs")],
        unwrap="workflow_runs", pagination=_gpg("workflow_runs")),
    _ga("trigger_workflow", "POST", "/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
        params=[*_OR(), _gpath("workflow_id"), _gb("ref", default="main"),
                _gb("inputs", ty="object")]),
    # Gists (create_gist is an escape hatch — files map is transformed per-value)
    _ga("list_gists", "GET", "/gists", params=[_glimit()], pagination=_gpg()),
    # Search (arg `query` -> wire `q`; order always sent, default desc)
    _ga("search_code", "GET", "/search/code",
        params=[_gq("query", "q", required=True), _glimit()], unwrap="items", pagination=_gpg("items")),
    _ga("search_repos", "GET", "/search/repositories",
        params=[_gq("query", "q", required=True), _gq("order", default="desc"), _gq("sort"), _glimit()],
        unwrap="items", pagination=_gpg("items")),
    _ga("search_issues", "GET", "/search/issues",
        params=[_gq("query", "q", required=True), _gq("order", default="desc"), _gq("sort"), _glimit()],
        unwrap="items", pagination=_gpg("items")),
    # Users / misc
    _ga("get_authenticated_user", "GET", "/user"),
    _ga("get_rate_limit", "GET", "/rate_limit"),
    _ga("star_repo", "PUT", "/user/starred/{owner}/{repo}", params=_OR()),
    _ga("unstar_repo", "DELETE", "/user/starred/{owner}/{repo}", params=_OR()),
]

GITHUB = ConnectorBinding(
    name="github",
    default_endpoint="main",
    endpoints={
        "main": EndpointBinding(
            id="main",
            base_url="https://api.github.com",
            encoding="json",
            auth_kind=AuthKind.BEARER,
            auth_header="Authorization",
            extra_headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        ),
    },
    actions={a.name: a for a in _GH},
    escape_hatches=["create_gist"],
)


ALL = {
    "airtable": AIRTABLE, "twilio": TWILIO, "shopify": SHOPIFY,
    "stripe": STRIPE, "github": GITHUB,
}
