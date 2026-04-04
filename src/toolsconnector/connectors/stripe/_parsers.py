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
    StripeCustomer,
    StripeInvoice,
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
