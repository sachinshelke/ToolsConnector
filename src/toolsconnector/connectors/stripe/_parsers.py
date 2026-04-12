"""Stripe API response parsers.

Helper functions to parse raw JSON dicts from the Stripe API
into typed Pydantic models.
"""

from __future__ import annotations

from typing import Any

from .types import (
    PaymentIntent,
    StripeAddress,
    StripeCharge,
    StripeCheckoutSession,
    StripeCustomer,
    StripeDispute,
    StripeEvent,
    StripeInvoice,
    StripePaymentMethod,
    StripePayout,
    StripePrice,
    StripeProduct,
    StripeRecurring,
    StripeRefund,
    StripeSetupIntent,
    StripeSubscription,
)


def parse_customer(data: dict[str, Any]) -> StripeCustomer:
    """Parse a StripeCustomer from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeCustomer instance.
    """
    address_data = data.get("address")
    return StripeCustomer(
        id=data["id"],
        object=data.get("object", "customer"),
        name=data.get("name"),
        email=data.get("email"),
        description=data.get("description"),
        phone=data.get("phone"),
        address=StripeAddress(**address_data) if address_data else None,
        balance=data.get("balance", 0),
        currency=data.get("currency"),
        default_source=data.get("default_source"),
        delinquent=data.get("delinquent", False),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_charge(data: dict[str, Any]) -> StripeCharge:
    """Parse a StripeCharge from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeCharge instance.
    """
    return StripeCharge(
        id=data["id"],
        object=data.get("object", "charge"),
        amount=data.get("amount", 0),
        amount_captured=data.get("amount_captured", 0),
        amount_refunded=data.get("amount_refunded", 0),
        currency=data.get("currency"),
        customer=data.get("customer"),
        description=data.get("description"),
        status=data.get("status"),
        paid=data.get("paid", False),
        refunded=data.get("refunded", False),
        captured=data.get("captured", False),
        payment_intent=data.get("payment_intent"),
        payment_method=data.get("payment_method"),
        receipt_url=data.get("receipt_url"),
        failure_code=data.get("failure_code"),
        failure_message=data.get("failure_message"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_invoice(data: dict[str, Any]) -> StripeInvoice:
    """Parse a StripeInvoice from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeInvoice instance.
    """
    return StripeInvoice(
        id=data["id"],
        object=data.get("object", "invoice"),
        customer=data.get("customer"),
        customer_email=data.get("customer_email"),
        customer_name=data.get("customer_name"),
        status=data.get("status"),
        currency=data.get("currency"),
        amount_due=data.get("amount_due", 0),
        amount_paid=data.get("amount_paid", 0),
        amount_remaining=data.get("amount_remaining", 0),
        total=data.get("total", 0),
        subtotal=data.get("subtotal", 0),
        tax=data.get("tax"),
        number=data.get("number"),
        invoice_pdf=data.get("invoice_pdf"),
        hosted_invoice_url=data.get("hosted_invoice_url"),
        due_date=data.get("due_date"),
        period_start=data.get("period_start"),
        period_end=data.get("period_end"),
        paid=data.get("paid", False),
        attempted=data.get("attempted", False),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_payment_intent(data: dict[str, Any]) -> PaymentIntent:
    """Parse a PaymentIntent from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A PaymentIntent instance.
    """
    return PaymentIntent(
        id=data["id"],
        object=data.get("object", "payment_intent"),
        amount=data.get("amount", 0),
        currency=data.get("currency"),
        customer=data.get("customer"),
        description=data.get("description"),
        status=data.get("status"),
        client_secret=data.get("client_secret"),
        payment_method=data.get("payment_method"),
        capture_method=data.get("capture_method"),
        confirmation_method=data.get("confirmation_method"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def flatten_metadata(metadata: dict[str, str]) -> dict[str, str]:
    """Flatten a metadata dict into Stripe form-encoding keys.

    Stripe expects metadata as ``metadata[key]=value`` in form data.

    Args:
        metadata: Dict of key-value metadata pairs.

    Returns:
        Flattened dict with ``metadata[key]`` keys.
    """
    return {f"metadata[{k}]": v for k, v in metadata.items()}


def parse_refund(data: dict[str, Any]) -> StripeRefund:
    """Parse a StripeRefund from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeRefund instance.
    """
    return StripeRefund(
        id=data["id"],
        object=data.get("object", "refund"),
        amount=data.get("amount", 0),
        currency=data.get("currency"),
        charge=data.get("charge"),
        payment_intent=data.get("payment_intent"),
        reason=data.get("reason"),
        status=data.get("status"),
        receipt_number=data.get("receipt_number"),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_subscription(data: dict[str, Any]) -> StripeSubscription:
    """Parse a StripeSubscription from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeSubscription instance.
    """
    return StripeSubscription(
        id=data["id"],
        object=data.get("object", "subscription"),
        customer=data.get("customer"),
        status=data.get("status"),
        current_period_start=data.get("current_period_start"),
        current_period_end=data.get("current_period_end"),
        cancel_at_period_end=data.get("cancel_at_period_end", False),
        canceled_at=data.get("canceled_at"),
        ended_at=data.get("ended_at"),
        trial_start=data.get("trial_start"),
        trial_end=data.get("trial_end"),
        default_payment_method=data.get("default_payment_method"),
        latest_invoice=data.get("latest_invoice"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_product(data: dict[str, Any]) -> StripeProduct:
    """Parse a StripeProduct from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeProduct instance.
    """
    return StripeProduct(
        id=data["id"],
        object=data.get("object", "product"),
        name=data.get("name"),
        description=data.get("description"),
        active=data.get("active", True),
        default_price=data.get("default_price"),
        images=data.get("images") or [],
        url=data.get("url"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
        updated=data.get("updated"),
    )


def parse_price(data: dict[str, Any]) -> StripePrice:
    """Parse a StripePrice from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripePrice instance.
    """
    recurring_data = data.get("recurring")
    recurring = None
    if recurring_data:
        recurring = StripeRecurring(
            interval=recurring_data.get("interval"),
            interval_count=recurring_data.get("interval_count", 1),
            usage_type=recurring_data.get("usage_type"),
        )

    return StripePrice(
        id=data["id"],
        object=data.get("object", "price"),
        product=data.get("product"),
        unit_amount=data.get("unit_amount"),
        currency=data.get("currency"),
        active=data.get("active", True),
        type=data.get("type"),
        recurring=recurring,
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_checkout_session(data: dict[str, Any]) -> StripeCheckoutSession:
    """Parse a StripeCheckoutSession from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeCheckoutSession instance.
    """
    return StripeCheckoutSession(
        id=data["id"],
        object=data.get("object", "checkout.session"),
        url=data.get("url"),
        mode=data.get("mode"),
        status=data.get("status"),
        payment_status=data.get("payment_status"),
        customer=data.get("customer"),
        customer_email=data.get("customer_email"),
        payment_intent=data.get("payment_intent"),
        subscription=data.get("subscription"),
        success_url=data.get("success_url"),
        cancel_url=data.get("cancel_url"),
        amount_total=data.get("amount_total"),
        currency=data.get("currency"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_payment_method(data: dict[str, Any]) -> StripePaymentMethod:
    """Parse a StripePaymentMethod from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripePaymentMethod instance.
    """
    return StripePaymentMethod(
        id=data["id"],
        object=data.get("object", "payment_method"),
        type=data.get("type"),
        customer=data.get("customer"),
        billing_details=data.get("billing_details"),
        card=data.get("card"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_dispute(data: dict[str, Any]) -> StripeDispute:
    """Parse a StripeDispute from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeDispute instance.
    """
    evidence = data.get("evidence_details") or {}
    return StripeDispute(
        id=data["id"],
        object=data.get("object", "dispute"),
        amount=data.get("amount", 0),
        currency=data.get("currency"),
        charge=data.get("charge"),
        payment_intent=data.get("payment_intent"),
        reason=data.get("reason"),
        status=data.get("status"),
        is_charge_refundable=data.get("is_charge_refundable", False),
        has_evidence=evidence.get("has_evidence", False),
        evidence_due_by=evidence.get("due_by"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_payout(data: dict[str, Any]) -> StripePayout:
    """Parse a StripePayout from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripePayout instance.
    """
    return StripePayout(
        id=data["id"],
        object=data.get("object", "payout"),
        amount=data.get("amount", 0),
        currency=data.get("currency"),
        status=data.get("status"),
        type=data.get("type"),
        method=data.get("method"),
        description=data.get("description"),
        destination=data.get("destination"),
        arrival_date=data.get("arrival_date"),
        failure_code=data.get("failure_code"),
        failure_message=data.get("failure_message"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )


def parse_event(data: dict[str, Any]) -> StripeEvent:
    """Parse a StripeEvent from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeEvent instance.
    """
    return StripeEvent(
        id=data["id"],
        object=data.get("object", "event"),
        type=data.get("type"),
        api_version=data.get("api_version"),
        data=data.get("data"),
        request=data.get("request"),
        pending_webhooks=data.get("pending_webhooks", 0),
        livemode=data.get("livemode", False),
        created=data.get("created"),
    )


def parse_setup_intent(data: dict[str, Any]) -> StripeSetupIntent:
    """Parse a StripeSetupIntent from API JSON.

    Args:
        data: Raw JSON dict from the Stripe API.

    Returns:
        A StripeSetupIntent instance.
    """
    return StripeSetupIntent(
        id=data["id"],
        object=data.get("object", "setup_intent"),
        status=data.get("status"),
        client_secret=data.get("client_secret"),
        customer=data.get("customer"),
        description=data.get("description"),
        payment_method=data.get("payment_method"),
        payment_method_types=data.get("payment_method_types") or [],
        usage=data.get("usage"),
        latest_attempt=data.get("latest_attempt"),
        livemode=data.get("livemode", False),
        metadata=data.get("metadata") or {},
        created=data.get("created"),
    )
