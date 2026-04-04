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
