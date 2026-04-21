"""Pydantic models for Stripe connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class StripeAddress(BaseModel):
    """A Stripe address object."""

    model_config = ConfigDict(frozen=True)

    city: Optional[str] = None
    country: Optional[str] = None
    line1: Optional[str] = None
    line2: Optional[str] = None
    postal_code: Optional[str] = None
    state: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class StripeCustomer(BaseModel):
    """A Stripe customer object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "customer"
    name: Optional[str] = None
    email: Optional[str] = None
    description: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[StripeAddress] = None
    balance: int = 0
    currency: Optional[str] = None
    default_source: Optional[str] = None
    delinquent: bool = False
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripeCharge(BaseModel):
    """A Stripe charge object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "charge"
    amount: int = 0
    amount_captured: int = 0
    amount_refunded: int = 0
    currency: Optional[str] = None
    customer: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    paid: bool = False
    refunded: bool = False
    captured: bool = False
    payment_intent: Optional[str] = None
    payment_method: Optional[str] = None
    receipt_url: Optional[str] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class PaymentIntent(BaseModel):
    """A Stripe PaymentIntent object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "payment_intent"
    amount: int = 0
    currency: Optional[str] = None
    customer: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    client_secret: Optional[str] = None
    payment_method: Optional[str] = None
    capture_method: Optional[str] = None
    confirmation_method: Optional[str] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripeInvoice(BaseModel):
    """A Stripe invoice object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "invoice"
    customer: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    status: Optional[str] = None
    currency: Optional[str] = None
    amount_due: int = 0
    amount_paid: int = 0
    amount_remaining: int = 0
    total: int = 0
    subtotal: int = 0
    tax: Optional[int] = None
    number: Optional[str] = None
    invoice_pdf: Optional[str] = None
    hosted_invoice_url: Optional[str] = None
    due_date: Optional[int] = None
    period_start: Optional[int] = None
    period_end: Optional[int] = None
    paid: bool = False
    attempted: bool = False
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripeBalanceAvailable(BaseModel):
    """Available balance breakdown by currency."""

    model_config = ConfigDict(frozen=True)

    amount: int = 0
    currency: str = "usd"
    source_types: dict[str, int] = Field(default_factory=dict)


class StripeBalancePending(BaseModel):
    """Pending balance breakdown by currency."""

    model_config = ConfigDict(frozen=True)

    amount: int = 0
    currency: str = "usd"
    source_types: dict[str, int] = Field(default_factory=dict)


class StripeBalance(BaseModel):
    """A Stripe balance object."""

    model_config = ConfigDict(frozen=True)

    object: str = "balance"
    available: list[StripeBalanceAvailable] = Field(default_factory=list)
    pending: list[StripeBalancePending] = Field(default_factory=list)
    livemode: bool = False


class StripeRefund(BaseModel):
    """A Stripe refund object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "refund"
    amount: int = 0
    currency: Optional[str] = None
    charge: Optional[str] = None
    payment_intent: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    receipt_number: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripeSubscription(BaseModel):
    """A Stripe subscription object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "subscription"
    customer: Optional[str] = None
    status: Optional[str] = None
    current_period_start: Optional[int] = None
    current_period_end: Optional[int] = None
    cancel_at_period_end: bool = False
    canceled_at: Optional[int] = None
    ended_at: Optional[int] = None
    trial_start: Optional[int] = None
    trial_end: Optional[int] = None
    default_payment_method: Optional[str] = None
    latest_invoice: Optional[str] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripeProduct(BaseModel):
    """A Stripe product object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "product"
    name: Optional[str] = None
    description: Optional[str] = None
    active: bool = True
    default_price: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None
    updated: Optional[int] = None


class StripeRecurring(BaseModel):
    """Recurring pricing configuration."""

    model_config = ConfigDict(frozen=True)

    interval: Optional[str] = None
    interval_count: int = 1
    usage_type: Optional[str] = None


class StripePrice(BaseModel):
    """A Stripe price object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "price"
    product: Optional[str] = None
    unit_amount: Optional[int] = None
    currency: Optional[str] = None
    active: bool = True
    type: Optional[str] = None
    recurring: Optional[StripeRecurring] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripeCheckoutSession(BaseModel):
    """A Stripe Checkout Session object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "checkout.session"
    url: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    payment_status: Optional[str] = None
    customer: Optional[str] = None
    customer_email: Optional[str] = None
    payment_intent: Optional[str] = None
    subscription: Optional[str] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    amount_total: Optional[int] = None
    currency: Optional[str] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripePaymentMethod(BaseModel):
    """A Stripe payment method object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "payment_method"
    type: Optional[str] = None
    customer: Optional[str] = None
    billing_details: Optional[dict[str, Any]] = None
    card: Optional[dict[str, Any]] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripeDispute(BaseModel):
    """A Stripe dispute (chargeback) object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "dispute"
    amount: int = 0
    currency: Optional[str] = None
    charge: Optional[str] = None
    payment_intent: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    is_charge_refundable: bool = False
    has_evidence: bool = False
    evidence_due_by: Optional[int] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripePayout(BaseModel):
    """A Stripe payout object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "payout"
    amount: int = 0
    currency: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    method: Optional[str] = None
    description: Optional[str] = None
    destination: Optional[str] = None
    arrival_date: Optional[int] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None


class StripeEvent(BaseModel):
    """A Stripe event (webhook event) object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "event"
    type: Optional[str] = None
    api_version: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    request: Optional[dict[str, Any]] = None
    pending_webhooks: int = 0
    livemode: bool = False
    created: Optional[int] = None


class StripeSetupIntent(BaseModel):
    """A Stripe SetupIntent object for collecting payment methods."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "setup_intent"
    status: Optional[str] = None
    client_secret: Optional[str] = None
    customer: Optional[str] = None
    description: Optional[str] = None
    payment_method: Optional[str] = None
    payment_method_types: list[str] = Field(default_factory=list)
    usage: Optional[str] = None
    latest_attempt: Optional[str] = None
    livemode: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    created: Optional[int] = None
