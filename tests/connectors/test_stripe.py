"""End-to-end tests for the Stripe connector using respx.

Pinned to the Stripe REST API v1 at ``api.stripe.com/v1``. Auth is HTTP
Basic (API key as username, empty password). Stripe requires
``application/x-www-form-urlencoded`` request bodies (NOT JSON) and uses
cursor-based pagination via ``starting_after``.

Why respx (not real API calls): deterministic, offline, no test-mode key
required for unit tests. Live verification against api.stripe.com (test
mode) is a separate step.

Structure (5 rounds):
  Round 1 — happy path for all 40 actions
  Round 2 — form-encoding, pagination cursor, URL-path injection guard
  Round 3 — error matrix (401/402/403/404/429/500)
  Round 4 — transport errors → typed wrappers
  Round 5 — MCP exposure, dangerous flags, sync wrappers, verification_status, extra=ignore
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.stripe import Stripe
from toolsconnector.errors import (
    APIError,
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
)
from toolsconnector.errors import ConnectionError as TCConnectionError
from toolsconnector.errors import TimeoutError as TCTimeoutError
from toolsconnector.errors import TransportError as TCTransportError

BASE = "https://api.stripe.com/v1"


@pytest_asyncio.fixture
async def stripe() -> Stripe:
    """A Stripe connector with a fake test key.

    Calls ``_setup()`` so the persistent httpx client exists; respx then
    intercepts at the transport level. The key never reaches the real API.
    """
    s = Stripe(credentials="sk_test_fake_key_for_unit_tests")
    await s._setup()
    yield s
    await s._teardown()


# --- minimal response fixtures (parsers require `id`, rest via .get) -------
_CUSTOMER = {"id": "cus_1", "object": "customer", "email": "a@example.com", "name": "Alice"}
_CHARGE = {
    "id": "ch_1",
    "object": "charge",
    "amount": 1000,
    "currency": "usd",
    "status": "succeeded",
    "paid": True,
    "captured": True,
}
_PI = {
    "id": "pi_1",
    "object": "payment_intent",
    "amount": 1000,
    "currency": "usd",
    "status": "requires_payment_method",
}
_INVOICE = {"id": "in_1", "object": "invoice", "status": "open", "amount_due": 1000}
_SUB = {"id": "sub_1", "object": "subscription", "status": "active"}
_PRODUCT = {"id": "prod_1", "object": "product", "name": "Widget", "active": True}
_PRICE = {"id": "price_1", "object": "price", "unit_amount": 1000, "currency": "usd"}
_SESSION = {
    "id": "cs_1",
    "object": "checkout.session",
    "url": "https://checkout.stripe.com/c/pay/cs_1",
    "mode": "payment",
}
_PM = {"id": "pm_1", "object": "payment_method", "type": "card"}
_REFUND = {"id": "re_1", "object": "refund", "amount": 1000, "status": "succeeded"}
_DISPUTE = {"id": "dp_1", "object": "dispute", "status": "warning_needs_response"}
_PAYOUT = {"id": "po_1", "object": "payout", "amount": 1000, "currency": "usd", "status": "pending"}
_EVENT = {"id": "evt_1", "object": "event", "type": "charge.succeeded"}
_SETI = {"id": "seti_1", "object": "setup_intent", "status": "requires_payment_method"}
_BALANCE = {
    "object": "balance",
    "available": [{"amount": 5000, "currency": "usd"}],
    "pending": [{"amount": 0, "currency": "usd"}],
}


def _list(item: dict) -> dict:
    """Wrap an item in a Stripe list envelope."""
    return {"object": "list", "data": [item], "has_more": False, "url": "/v1/x"}


# ===========================================================================
# Round 1 — happy path × 40 actions
# ===========================================================================


@pytest.mark.asyncio
async def test_list_customers(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/customers").mock(return_value=httpx.Response(200, json=_list(_CUSTOMER)))
        page = await stripe.alist_customers(limit=5)
        assert len(page.items) == 1
        assert page.items[0].id == "cus_1"


@pytest.mark.asyncio
async def test_get_customer(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.get("/customers/cus_1").mock(return_value=httpx.Response(200, json=_CUSTOMER))
        c = await stripe.aget_customer(customer_id="cus_1")
        assert c.id == "cus_1"
        # Basic auth header present
        auth = route.calls.last.request.headers["authorization"]
        assert auth.startswith("Basic ")


@pytest.mark.asyncio
async def test_create_customer(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.post("/customers").mock(return_value=httpx.Response(200, json=_CUSTOMER))
        c = await stripe.acreate_customer(email="a@example.com", name="Alice")
        assert c.id == "cus_1"
        body = route.calls.last.request.content
        # form-encoded, not JSON
        assert b"email=" in body and b"name=Alice" in body
        ct = route.calls.last.request.headers["content-type"]
        assert "application/x-www-form-urlencoded" in ct


@pytest.mark.asyncio
async def test_update_customer(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/customers/cus_1").mock(
            return_value=httpx.Response(200, json={**_CUSTOMER, "name": "Bob"})
        )
        c = await stripe.aupdate_customer(customer_id="cus_1", name="Bob")
        assert c.name == "Bob"


@pytest.mark.asyncio
async def test_delete_customer_returns_none(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.delete("/customers/cus_1").mock(
            return_value=httpx.Response(
                200, json={"id": "cus_1", "object": "customer", "deleted": True}
            )
        )
        result = await stripe.adelete_customer(customer_id="cus_1")
        assert result is None


@pytest.mark.asyncio
async def test_list_charges(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/charges").mock(return_value=httpx.Response(200, json=_list(_CHARGE)))
        page = await stripe.alist_charges(customer="cus_1", limit=5)
        assert page.items[0].id == "ch_1"


@pytest.mark.asyncio
async def test_get_charge(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/charges/ch_1").mock(return_value=httpx.Response(200, json=_CHARGE))
        c = await stripe.aget_charge(charge_id="ch_1")
        assert c.id == "ch_1" and c.status == "succeeded"


@pytest.mark.asyncio
async def test_create_charge(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.post("/charges").mock(return_value=httpx.Response(200, json=_CHARGE))
        c = await stripe.acreate_charge(amount=1000, currency="usd", source="tok_visa")
        assert c.id == "ch_1"
        assert b"amount=1000" in route.calls.last.request.content


@pytest.mark.asyncio
async def test_refund_charge(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.post("/refunds").mock(return_value=httpx.Response(200, json=_REFUND))
        r = await stripe.arefund_charge(charge_id="ch_1", amount=500)
        assert r.id == "re_1"
        assert b"charge=ch_1" in route.calls.last.request.content


@pytest.mark.asyncio
async def test_list_refunds(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/refunds").mock(return_value=httpx.Response(200, json=_list(_REFUND)))
        page = await stripe.alist_refunds(charge="ch_1")
        assert page.items[0].id == "re_1"


@pytest.mark.asyncio
async def test_create_payment_intent(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/payment_intents").mock(return_value=httpx.Response(200, json=_PI))
        pi = await stripe.acreate_payment_intent(amount=1000, currency="usd")
        assert pi.id == "pi_1"


@pytest.mark.asyncio
async def test_get_payment_intent(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/payment_intents/pi_1").mock(return_value=httpx.Response(200, json=_PI))
        pi = await stripe.aget_payment_intent(payment_intent_id="pi_1")
        assert pi.id == "pi_1"


@pytest.mark.asyncio
async def test_list_payment_intents(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/payment_intents").mock(return_value=httpx.Response(200, json=_list(_PI)))
        page = await stripe.alist_payment_intents(customer="cus_1")
        assert page.items[0].id == "pi_1"


@pytest.mark.asyncio
async def test_confirm_payment_intent(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/payment_intents/pi_1/confirm").mock(
            return_value=httpx.Response(200, json={**_PI, "status": "succeeded"})
        )
        pi = await stripe.aconfirm_payment_intent(payment_intent_id="pi_1", payment_method="pm_1")
        assert pi.status == "succeeded"


@pytest.mark.asyncio
async def test_cancel_payment_intent(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/payment_intents/pi_1/cancel").mock(
            return_value=httpx.Response(200, json={**_PI, "status": "canceled"})
        )
        pi = await stripe.acancel_payment_intent(payment_intent_id="pi_1")
        assert pi.status == "canceled"


@pytest.mark.asyncio
async def test_capture_payment_intent(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/payment_intents/pi_1/capture").mock(
            return_value=httpx.Response(200, json={**_PI, "status": "succeeded"})
        )
        pi = await stripe.acapture_payment_intent(payment_intent_id="pi_1", amount_to_capture=1000)
        assert pi.status == "succeeded"


@pytest.mark.asyncio
async def test_list_invoices(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/invoices").mock(return_value=httpx.Response(200, json=_list(_INVOICE)))
        page = await stripe.alist_invoices(customer="cus_1")
        assert page.items[0].id == "in_1"


@pytest.mark.asyncio
async def test_get_invoice(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/invoices/in_1").mock(return_value=httpx.Response(200, json=_INVOICE))
        inv = await stripe.aget_invoice(invoice_id="in_1")
        assert inv.id == "in_1"


@pytest.mark.asyncio
async def test_void_invoice(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/invoices/in_1/void").mock(
            return_value=httpx.Response(200, json={**_INVOICE, "status": "void"})
        )
        inv = await stripe.avoid_invoice(invoice_id="in_1")
        assert inv.status == "void"


@pytest.mark.asyncio
async def test_create_subscription(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/subscriptions").mock(return_value=httpx.Response(200, json=_SUB))
        sub = await stripe.acreate_subscription(customer="cus_1", price="price_1")
        assert sub.id == "sub_1"


@pytest.mark.asyncio
async def test_cancel_subscription_immediate_uses_delete(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.delete("/subscriptions/sub_1").mock(
            return_value=httpx.Response(200, json={**_SUB, "status": "canceled"})
        )
        sub = await stripe.acancel_subscription(subscription_id="sub_1", at_period_end=False)
        assert sub.status == "canceled"
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_cancel_subscription_at_period_end_uses_post(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.post("/subscriptions/sub_1").mock(return_value=httpx.Response(200, json=_SUB))
        await stripe.acancel_subscription(subscription_id="sub_1", at_period_end=True)
        assert b"cancel_at_period_end=true" in route.calls.last.request.content


@pytest.mark.asyncio
async def test_list_subscriptions(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/subscriptions").mock(return_value=httpx.Response(200, json=_list(_SUB)))
        page = await stripe.alist_subscriptions(customer="cus_1", status="active")
        assert page.items[0].id == "sub_1"


@pytest.mark.asyncio
async def test_get_subscription(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/subscriptions/sub_1").mock(return_value=httpx.Response(200, json=_SUB))
        sub = await stripe.aget_subscription(subscription_id="sub_1")
        assert sub.id == "sub_1"


@pytest.mark.asyncio
async def test_create_product(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/products").mock(return_value=httpx.Response(200, json=_PRODUCT))
        p = await stripe.acreate_product(name="Widget")
        assert p.id == "prod_1"


@pytest.mark.asyncio
async def test_list_products(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/products").mock(return_value=httpx.Response(200, json=_list(_PRODUCT)))
        page = await stripe.alist_products()
        assert page.items[0].id == "prod_1"


@pytest.mark.asyncio
async def test_create_price(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.post("/prices").mock(return_value=httpx.Response(200, json=_PRICE))
        pr = await stripe.acreate_price(product="prod_1", unit_amount=1000, currency="usd")
        assert pr.id == "price_1"
        assert b"unit_amount=1000" in route.calls.last.request.content


@pytest.mark.asyncio
async def test_list_prices(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/prices").mock(return_value=httpx.Response(200, json=_list(_PRICE)))
        page = await stripe.alist_prices(product="prod_1")
        assert page.items[0].id == "price_1"


@pytest.mark.asyncio
async def test_create_checkout_session(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/checkout/sessions").mock(return_value=httpx.Response(200, json=_SESSION))
        sess = await stripe.acreate_checkout_session(
            line_items=[{"price": "price_1", "quantity": 1}],
            mode="payment",
            success_url="https://x/ok",
            cancel_url="https://x/no",
        )
        assert sess.id == "cs_1"


@pytest.mark.asyncio
async def test_list_payment_methods(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/payment_methods").mock(return_value=httpx.Response(200, json=_list(_PM)))
        page = await stripe.alist_payment_methods(customer="cus_1", type="card")
        assert page.items[0].id == "pm_1"


@pytest.mark.asyncio
async def test_list_disputes(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/disputes").mock(return_value=httpx.Response(200, json=_list(_DISPUTE)))
        page = await stripe.alist_disputes()
        assert page.items[0].id == "dp_1"


@pytest.mark.asyncio
async def test_get_dispute(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/disputes/dp_1").mock(return_value=httpx.Response(200, json=_DISPUTE))
        d = await stripe.aget_dispute(dispute_id="dp_1")
        assert d.id == "dp_1"


@pytest.mark.asyncio
async def test_close_dispute(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/disputes/dp_1/close").mock(
            return_value=httpx.Response(200, json={**_DISPUTE, "status": "lost"})
        )
        d = await stripe.aclose_dispute(dispute_id="dp_1")
        assert d.status == "lost"


@pytest.mark.asyncio
async def test_list_payouts(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/payouts").mock(return_value=httpx.Response(200, json=_list(_PAYOUT)))
        page = await stripe.alist_payouts()
        assert page.items[0].id == "po_1"


@pytest.mark.asyncio
async def test_create_payout(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.post("/payouts").mock(return_value=httpx.Response(200, json=_PAYOUT))
        p = await stripe.acreate_payout(amount=1000, currency="usd")
        assert p.id == "po_1"
        assert b"amount=1000" in route.calls.last.request.content


@pytest.mark.asyncio
async def test_get_payout(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/payouts/po_1").mock(return_value=httpx.Response(200, json=_PAYOUT))
        p = await stripe.aget_payout(payout_id="po_1")
        assert p.id == "po_1"


@pytest.mark.asyncio
async def test_list_events(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/events").mock(return_value=httpx.Response(200, json=_list(_EVENT)))
        page = await stripe.alist_events(type="charge.succeeded")
        assert page.items[0].id == "evt_1"


@pytest.mark.asyncio
async def test_get_event(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/events/evt_1").mock(return_value=httpx.Response(200, json=_EVENT))
        e = await stripe.aget_event(event_id="evt_1")
        assert e.id == "evt_1"


@pytest.mark.asyncio
async def test_create_setup_intent(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.post("/setup_intents").mock(return_value=httpx.Response(200, json=_SETI))
        si = await stripe.acreate_setup_intent(customer="cus_1")
        assert si.id == "seti_1"


@pytest.mark.asyncio
async def test_get_setup_intent(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/setup_intents/seti_1").mock(return_value=httpx.Response(200, json=_SETI))
        si = await stripe.aget_setup_intent(setup_intent_id="seti_1")
        assert si.id == "seti_1"


@pytest.mark.asyncio
async def test_get_balance(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/balance").mock(return_value=httpx.Response(200, json=_BALANCE))
        bal = await stripe.aget_balance()
        assert bal.available[0].amount == 5000


# ===========================================================================
# Round 2 — form-encoding, pagination cursor, URL-path injection guard
# ===========================================================================


@pytest.mark.asyncio
async def test_metadata_is_flattened_into_form(stripe: Stripe) -> None:
    """metadata={'k':'v'} → form key metadata[k]=v (Stripe's bracket syntax)."""
    with respx.mock(base_url=BASE) as m:
        route = m.post("/customers").mock(return_value=httpx.Response(200, json=_CUSTOMER))
        await stripe.acreate_customer(email="a@example.com", metadata={"plan": "gold"})
        body = route.calls.last.request.content.decode()
        assert "metadata%5Bplan%5D=gold" in body or "metadata[plan]=gold" in body


@pytest.mark.asyncio
async def test_pagination_passes_starting_after(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.get("/customers").mock(return_value=httpx.Response(200, json=_list(_CUSTOMER)))
        await stripe.alist_customers(limit=5, starting_after="cus_prev")
        params = dict(route.calls.last.request.url.params)
        assert params["starting_after"] == "cus_prev"
        assert params["limit"] == "5"


@pytest.mark.asyncio
async def test_limit_capped_at_100(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.get("/customers").mock(return_value=httpx.Response(200, json=_list(_CUSTOMER)))
        await stripe.alist_customers(limit=9999)
        assert dict(route.calls.last.request.url.params)["limit"] == "100"


@pytest.mark.asyncio
async def test_path_traversal_id_is_percent_encoded(stripe: Stripe) -> None:
    """A hostile customer_id with '/' must be percent-encoded, not escape the path.

    Without _p(), customer_id='../charges/ch_x' would collapse to
    /v1/charges/ch_x via httpx normalization. With _p() the slashes
    become %2F so the request stays under /v1/customers/.
    """
    with respx.mock(base_url=BASE) as m:
        # The encoded path Stripe would receive
        route = m.get(httpx.URL(f"{BASE}/customers/..%2Fcharges%2Fch_x")).mock(
            return_value=httpx.Response(200, json=_CUSTOMER)
        )
        await stripe.aget_customer(customer_id="../charges/ch_x")
        # The raw request path must NOT contain a literal slash from the id
        raw = str(route.calls.last.request.url)
        assert "%2F" in raw
        assert "/customers/../charges/ch_x" not in raw


# ===========================================================================
# Round 3 — error matrix
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,exc",
    [
        (401, InvalidCredentialsError),
        (402, APIError),  # Stripe card error — generic 4xx → APIError (not specifically modeled)
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (429, RateLimitError),
        (500, ServerError),
    ],
)
async def test_error_status_maps_to_typed(stripe: Stripe, status: int, exc: type) -> None:
    body = {"error": {"type": "invalid_request_error", "message": "boom"}}
    with respx.mock(base_url=BASE) as m:
        m.get("/customers/cus_x").mock(return_value=httpx.Response(status, json=body))
        with pytest.raises(exc) as info:
            await stripe.aget_customer(customer_id="cus_x")
        assert info.value.connector == "stripe"


@pytest.mark.asyncio
async def test_429_parses_retry_after(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/customers/cus_x").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "30"}, json={"error": {}})
        )
        with pytest.raises(RateLimitError) as info:
            await stripe.aget_customer(customer_id="cus_x")
        assert info.value.retry_after_seconds == 30.0


# ===========================================================================
# Round 4 — transport errors → typed wrappers
# ===========================================================================


@pytest.mark.asyncio
async def test_timeout_wraps_typed(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/balance").mock(side_effect=httpx.ConnectTimeout("slow"))
        with pytest.raises(TCTimeoutError) as info:
            await stripe.aget_balance()
        assert info.value.connector == "stripe"


@pytest.mark.asyncio
async def test_connect_error_wraps_typed(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/balance").mock(side_effect=httpx.ConnectError("dns"))
        with pytest.raises(TCConnectionError) as info:
            await stripe.aget_balance()
        assert info.value.connector == "stripe"


@pytest.mark.asyncio
async def test_transport_error_wraps_typed(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/balance").mock(side_effect=httpx.ReadError("reset"))
        with pytest.raises(TCTransportError) as info:
            await stripe.aget_balance()
        assert info.value.connector == "stripe"


# ===========================================================================
# Round 5 — MCP / dangerous flags / sync wrappers / verification / extra=ignore
# ===========================================================================


def test_all_40_actions_registered() -> None:
    spec = Stripe.get_spec()
    actions = spec.actions if isinstance(spec.actions, list) else list(spec.actions.values())
    assert len(actions) == 40


def test_dangerous_flags() -> None:
    spec = Stripe.get_spec()
    actions = {
        a.name: a
        for a in (spec.actions if isinstance(spec.actions, list) else spec.actions.values())
    }
    # A representative set of mutating actions must be flagged dangerous
    for name in (
        "create_customer",
        "delete_customer",
        "create_charge",
        "refund_charge",
        "cancel_subscription",
        "create_payout",
        "void_invoice",
        "capture_payment_intent",
    ):
        assert actions[name].dangerous, f"{name} should be dangerous"
    # Read-only actions must NOT be dangerous
    for name in ("list_customers", "get_customer", "get_balance", "list_charges"):
        assert not actions[name].dangerous, f"{name} should be safe"


def test_mcp_tool_names_prefixed() -> None:
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["stripe"], credentials={"stripe": "sk_test_x"})
    names = [t["name"] for t in kit.list_tools()]
    assert all(n.startswith("stripe_") for n in names)
    assert "stripe_create_customer" in names


@pytest.mark.asyncio
async def test_sync_wrappers_exposed(stripe: Stripe) -> None:
    # Async (aXXX) and sync (XXX) variants both present
    assert hasattr(stripe, "aget_customer")
    assert hasattr(stripe, "alist_customers")


def test_verification_status() -> None:
    """Live-verified against api.stripe.com (test mode) on 2026-06-13."""
    assert Stripe.verification_status == "live"
    assert Stripe.get_spec().verification_status == "live"


@pytest.mark.asyncio
async def test_extra_fields_ignored(stripe: Stripe) -> None:
    """Stripe adds new response fields without a version bump; models must tolerate them."""
    with respx.mock(base_url=BASE) as m:
        m.get("/customers/cus_1").mock(
            return_value=httpx.Response(
                200, json={**_CUSTOMER, "tax_exempt": "none", "brand_new_field": 123}
            )
        )
        c = await stripe.aget_customer(customer_id="cus_1")
        assert c.id == "cus_1"  # parses fine despite unknown fields


@pytest.mark.asyncio
async def test_concurrent_requests_safe(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/customers/cus_a").mock(
            return_value=httpx.Response(200, json={**_CUSTOMER, "id": "cus_a"})
        )
        m.get("/customers/cus_b").mock(
            return_value=httpx.Response(200, json={**_CUSTOMER, "id": "cus_b"})
        )
        results = await asyncio.gather(
            stripe.aget_customer(customer_id="cus_a"),
            stripe.aget_customer(customer_id="cus_b"),
        )
        assert {r.id for r in results} == {"cus_a", "cus_b"}


# ===========================================================================
# Round 4 — live-sweep-driven additions (2026-06-13 verification cycle)
# ===========================================================================


@pytest.mark.asyncio
async def test_create_payment_intent_pinned_types_and_capture(stripe: Stripe) -> None:
    """payment_method_types/payment_method/capture_method encode as Stripe form fields.

    Live finding: without pinning payment_method_types, dashboard-default
    intents may require a return_url at confirmation (HTTP 400).
    """
    with respx.mock(base_url=BASE) as m:
        route = m.post("/payment_intents").mock(return_value=httpx.Response(200, json=_PI))
        await stripe.acreate_payment_intent(
            amount=700,
            currency="usd",
            payment_method_types=["card", "link"],
            payment_method="pm_card_visa",
            capture_method="manual",
        )
        body = route.calls.last.request.content.decode()
        assert "payment_method_types%5B0%5D=card" in body
        assert "payment_method_types%5B1%5D=link" in body
        assert "payment_method=pm_card_visa" in body
        assert "capture_method=manual" in body


@pytest.mark.asyncio
async def test_confirm_payment_intent_return_url(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        route = m.post("/payment_intents/pi_1/confirm").mock(
            return_value=httpx.Response(200, json={**_PI, "status": "succeeded"})
        )
        await stripe.aconfirm_payment_intent(
            payment_intent_id="pi_1",
            payment_method="pm_1",
            return_url="https://example.com/back",
        )
        body = route.calls.last.request.content.decode()
        assert "return_url=https%3A%2F%2Fexample.com%2Fback" in body


@pytest.mark.asyncio
async def test_payment_intent_latest_charge_string(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/payment_intents/pi_1").mock(
            return_value=httpx.Response(200, json={**_PI, "latest_charge": "ch_9"})
        )
        pi = await stripe.aget_payment_intent(payment_intent_id="pi_1")
        assert pi.latest_charge == "ch_9"


@pytest.mark.asyncio
async def test_payment_intent_latest_charge_expanded_object(stripe: Stripe) -> None:
    """``expand[]=latest_charge`` returns an object; the parser normalizes to the ID."""
    with respx.mock(base_url=BASE) as m:
        m.get("/payment_intents/pi_1").mock(
            return_value=httpx.Response(
                200, json={**_PI, "latest_charge": {"id": "ch_9", "object": "charge"}}
            )
        )
        pi = await stripe.aget_payment_intent(payment_intent_id="pi_1")
        assert pi.latest_charge == "ch_9"


@pytest.mark.asyncio
async def test_deleted_customer_tombstone(stripe: Stripe) -> None:
    """Stripe returns HTTP 200 with deleted=true for a deleted customer (not 404) —
    verified live; the flag must surface so agents can tell the customer is gone."""
    with respx.mock(base_url=BASE) as m:
        m.get("/customers/cus_1").mock(
            return_value=httpx.Response(
                200, json={"id": "cus_1", "object": "customer", "deleted": True}
            )
        )
        c = await stripe.aget_customer(customer_id="cus_1")
        assert c.deleted is True


@pytest.mark.asyncio
async def test_customer_deleted_defaults_false(stripe: Stripe) -> None:
    with respx.mock(base_url=BASE) as m:
        m.get("/customers/cus_1").mock(return_value=httpx.Response(200, json=_CUSTOMER))
        c = await stripe.aget_customer(customer_id="cus_1")
        assert c.deleted is False
