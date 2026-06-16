"""Declarative HTTP binding for the Stripe connector.

Extracted from experiments/sdk_spike/specs.py. This is the production binding
that makes the Stripe connector load-bearing in Python (Phase 1 migration).
All 39 of 40 actions are bound declaratively; cancel_subscription is the
documented escape hatch (HTTP method switches POST/DELETE on an arg value).
"""

from __future__ import annotations

from toolsconnector.spec.binding import (
    ActionBinding,
    AuthKind,
    ConnectorBinding,
    EndpointBinding,
    Location,
    PaginationBinding,
    PaginationKind,
    ParamBinding,
    Style,
)


def _p(name, wire, loc, **kw):
    return ParamBinding(name=name, wire=wire, location=loc, **kw)


def _list(name, *extra_filters):
    """A standard Stripe list action: GET /{name}?limit&starting_after[&filters],
    with cursor pagination (next starting_after = id of the last item, while has_more)."""
    return ActionBinding(
        name=f"list_{name}",
        method="GET",
        endpoint="main",
        path=f"/{name}",
        unwrap="data",
        params=[
            *extra_filters,
            _p("limit", "limit", Location.QUERY, max=100, default=10),
            _p("starting_after", "starting_after", Location.QUERY),
        ],
        pagination=PaginationBinding(
            kind=PaginationKind.LAST_ID,
            items_field="data",
            token_param_py="starting_after",
        ),
    )


_META = _p("metadata", "metadata", Location.BODY, style=Style.MAP)  # metadata[k]=v


STRIPE = ConnectorBinding(
    name="stripe",
    default_endpoint="main",
    endpoints={
        "main": EndpointBinding(
            id="main",
            base_url="https://api.stripe.com/v1",
            encoding="form",
            auth_kind=AuthKind.BASIC_USER,
            auth_header="Authorization",
        ),
    },
    actions={
        # ---- Customers ----
        "list_customers": _list("customers"),
        "get_customer": ActionBinding(
            name="get_customer",
            method="GET",
            endpoint="main",
            path="/customers/{customer_id}",
            params=[_p("customer_id", "customer_id", Location.PATH)],
        ),
        "create_customer": ActionBinding(
            name="create_customer",
            method="POST",
            endpoint="main",
            path="/customers",
            params=[
                _p("email", "email", Location.BODY),
                _p("name", "name", Location.BODY),
                _p("description", "description", Location.BODY),
                _META,
            ],
        ),
        "update_customer": ActionBinding(
            name="update_customer",
            method="POST",
            endpoint="main",
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
            name="delete_customer",
            method="DELETE",
            endpoint="main",
            path="/customers/{customer_id}",
            params=[_p("customer_id", "customer_id", Location.PATH)],
        ),
        # ---- Charges ----
        "list_charges": _list("charges", _p("customer", "customer", Location.QUERY)),
        "get_charge": ActionBinding(
            name="get_charge",
            method="GET",
            endpoint="main",
            path="/charges/{charge_id}",
            params=[_p("charge_id", "charge_id", Location.PATH)],
        ),
        "create_charge": ActionBinding(
            name="create_charge",
            method="POST",
            endpoint="main",
            path="/charges",
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
            name="refund_charge",
            method="POST",
            endpoint="main",
            path="/refunds",
            params=[
                _p("charge_id", "charge", Location.BODY),
                _p("amount", "amount", Location.BODY),
                _p("reason", "reason", Location.BODY),
            ],
        ),
        "list_refunds": _list("refunds", _p("charge", "charge", Location.QUERY)),
        # ---- PaymentIntents ----
        "create_payment_intent": ActionBinding(
            name="create_payment_intent",
            method="POST",
            endpoint="main",
            path="/payment_intents",
            params=[
                _p("amount", "amount", Location.BODY),
                _p("currency", "currency", Location.BODY),
                _p("customer", "customer", Location.BODY),
                _p("description", "description", Location.BODY),
                _p(
                    "payment_method_types",
                    "payment_method_types",
                    Location.BODY,
                    style=Style.INDEXED,
                ),
                _p("payment_method", "payment_method", Location.BODY),
                _p("capture_method", "capture_method", Location.BODY),
            ],
        ),
        "get_payment_intent": ActionBinding(
            name="get_payment_intent",
            method="GET",
            endpoint="main",
            path="/payment_intents/{payment_intent_id}",
            params=[_p("payment_intent_id", "payment_intent_id", Location.PATH)],
        ),
        "list_payment_intents": _list(
            "payment_intents", _p("customer", "customer", Location.QUERY)
        ),
        "confirm_payment_intent": ActionBinding(
            name="confirm_payment_intent",
            method="POST",
            endpoint="main",
            path="/payment_intents/{payment_intent_id}/confirm",
            params=[
                _p("payment_intent_id", "payment_intent_id", Location.PATH),
                _p("payment_method", "payment_method", Location.BODY),
                _p("return_url", "return_url", Location.BODY),
            ],
        ),
        "cancel_payment_intent": ActionBinding(
            name="cancel_payment_intent",
            method="POST",
            endpoint="main",
            path="/payment_intents/{payment_intent_id}/cancel",
            params=[_p("payment_intent_id", "payment_intent_id", Location.PATH)],
        ),
        "capture_payment_intent": ActionBinding(
            name="capture_payment_intent",
            method="POST",
            endpoint="main",
            path="/payment_intents/{payment_intent_id}/capture",
            params=[
                _p("payment_intent_id", "payment_intent_id", Location.PATH),
                _p("amount_to_capture", "amount_to_capture", Location.BODY),
            ],
        ),
        # ---- Invoices ----
        "list_invoices": _list("invoices", _p("customer", "customer", Location.QUERY)),
        "get_invoice": ActionBinding(
            name="get_invoice",
            method="GET",
            endpoint="main",
            path="/invoices/{invoice_id}",
            params=[_p("invoice_id", "invoice_id", Location.PATH)],
        ),
        "void_invoice": ActionBinding(
            name="void_invoice",
            method="POST",
            endpoint="main",
            path="/invoices/{invoice_id}/void",
            params=[_p("invoice_id", "invoice_id", Location.PATH)],
        ),
        # ---- Balance ----
        "get_balance": ActionBinding(
            name="get_balance",
            method="GET",
            endpoint="main",
            path="/balance",
        ),
        # ---- Subscriptions (cancel_subscription = escape hatch, not bound) ----
        "create_subscription": ActionBinding(
            name="create_subscription",
            method="POST",
            endpoint="main",
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
            _p("status", "status", Location.QUERY),
        ),
        "get_subscription": ActionBinding(
            name="get_subscription",
            method="GET",
            endpoint="main",
            path="/subscriptions/{subscription_id}",
            params=[_p("subscription_id", "subscription_id", Location.PATH)],
        ),
        # ---- Products ----
        "create_product": ActionBinding(
            name="create_product",
            method="POST",
            endpoint="main",
            path="/products",
            params=[
                _p("name", "name", Location.BODY),
                _p("description", "description", Location.BODY),
                _META,
            ],
        ),
        "list_products": _list("products"),
        # ---- Prices ----
        "create_price": ActionBinding(
            name="create_price",
            method="POST",
            endpoint="main",
            path="/prices",
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
            name="create_checkout_session",
            method="POST",
            endpoint="main",
            path="/checkout/sessions",
            params=[
                _p("mode", "mode", Location.BODY),
                _p("success_url", "success_url", Location.BODY),
                _p("cancel_url", "cancel_url", Location.BODY),
                _p(
                    "line_items",
                    "line_items",
                    Location.BODY,
                    style=Style.INDEXED_OBJECT,
                    subkeys=["price", "quantity"],
                    subkey_defaults={"quantity": 1},
                ),
            ],
        ),
        # ---- Payment Methods ----
        "list_payment_methods": ActionBinding(
            name="list_payment_methods",
            method="GET",
            endpoint="main",
            path="/payment_methods",
            unwrap="data",
            params=[
                _p("customer", "customer", Location.QUERY),
                _p("type", "type", Location.QUERY),
                _p("limit", "limit", Location.QUERY, max=100, default=10),
                _p("starting_after", "starting_after", Location.QUERY),
            ],
            pagination=PaginationBinding(
                kind=PaginationKind.LAST_ID,
                items_field="data",
                token_param_py="starting_after",
            ),
        ),
        # ---- Disputes ----
        "list_disputes": _list("disputes"),
        "get_dispute": ActionBinding(
            name="get_dispute",
            method="GET",
            endpoint="main",
            path="/disputes/{dispute_id}",
            params=[_p("dispute_id", "dispute_id", Location.PATH)],
        ),
        "close_dispute": ActionBinding(
            name="close_dispute",
            method="POST",
            endpoint="main",
            path="/disputes/{dispute_id}/close",
            params=[_p("dispute_id", "dispute_id", Location.PATH)],
        ),
        # ---- Payouts ----
        "list_payouts": _list("payouts"),
        "create_payout": ActionBinding(
            name="create_payout",
            method="POST",
            endpoint="main",
            path="/payouts",
            params=[
                _p("amount", "amount", Location.BODY),
                _p("currency", "currency", Location.BODY),
            ],
        ),
        "get_payout": ActionBinding(
            name="get_payout",
            method="GET",
            endpoint="main",
            path="/payouts/{payout_id}",
            params=[_p("payout_id", "payout_id", Location.PATH)],
        ),
        # ---- Events ----
        "list_events": _list("events", _p("type", "type", Location.QUERY)),
        "get_event": ActionBinding(
            name="get_event",
            method="GET",
            endpoint="main",
            path="/events/{event_id}",
            params=[_p("event_id", "event_id", Location.PATH)],
        ),
        # ---- SetupIntents ----
        "create_setup_intent": ActionBinding(
            name="create_setup_intent",
            method="POST",
            endpoint="main",
            path="/setup_intents",
            params=[
                _p("customer", "customer", Location.BODY),
                _p(
                    "payment_method_types",
                    "payment_method_types",
                    Location.BODY,
                    style=Style.INDEXED,
                ),
            ],
        ),
        "get_setup_intent": ActionBinding(
            name="get_setup_intent",
            method="GET",
            endpoint="main",
            path="/setup_intents/{setup_intent_id}",
            params=[_p("setup_intent_id", "setup_intent_id", Location.PATH)],
        ),
    },
    # cancel_subscription: HTTP method switches POST (cancel_at_period_end) <->
    # DELETE (immediate) on an arg — generated as a typed method delegating to a
    # per-language override, so the SDK surface includes all 40 actions.
    escape_hatches=["cancel_subscription"],
)

STRIPE_BINDING = STRIPE
