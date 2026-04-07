"""Pydantic models for Plaid connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlaidAccount(BaseModel):
    """A Plaid financial account."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    name: str = ""
    official_name: Optional[str] = None
    type: str = ""
    subtype: Optional[str] = None
    mask: Optional[str] = None
    balances: Optional[dict[str, Any]] = None
    verification_status: Optional[str] = None
    persistent_account_id: Optional[str] = None

    @property
    def current_balance(self) -> Optional[float]:
        """Shortcut to the current balance."""
        if self.balances:
            return self.balances.get("current")
        return None

    @property
    def available_balance(self) -> Optional[float]:
        """Shortcut to the available balance."""
        if self.balances:
            return self.balances.get("available")
        return None


class PlaidTransaction(BaseModel):
    """A Plaid financial transaction."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    account_id: str = ""
    amount: float = 0.0
    name: str = ""
    merchant_name: Optional[str] = None
    date: str = ""
    datetime: Optional[str] = None
    authorized_date: Optional[str] = None
    pending: bool = False
    category: list[str] = Field(default_factory=list)
    category_id: Optional[str] = None
    payment_channel: Optional[str] = None
    iso_currency_code: Optional[str] = None
    unofficial_currency_code: Optional[str] = None
    location: Optional[dict[str, Any]] = None
    payment_meta: Optional[dict[str, Any]] = None
    personal_finance_category: Optional[dict[str, str]] = None


class PlaidBalance(BaseModel):
    """Balance information for a Plaid account."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    current: Optional[float] = None
    available: Optional[float] = None
    limit: Optional[float] = None
    iso_currency_code: Optional[str] = None
    unofficial_currency_code: Optional[str] = None
    last_updated_datetime: Optional[str] = None


class PlaidInstitution(BaseModel):
    """A Plaid-supported financial institution."""

    model_config = ConfigDict(frozen=True)

    institution_id: str
    name: str = ""
    products: list[str] = Field(default_factory=list)
    country_codes: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    primary_color: Optional[str] = None
    logo: Optional[str] = None
    routing_numbers: list[str] = Field(default_factory=list)
    oauth: bool = False


class PlaidLinkToken(BaseModel):
    """A Plaid Link token for client-side initialization."""

    model_config = ConfigDict(frozen=True)

    link_token: str
    expiration: str = ""
    request_id: str = ""


class PlaidHolding(BaseModel):
    """An investment holding from Plaid."""

    model_config = ConfigDict(frozen=True)

    account_id: str = ""
    security_id: Optional[str] = None
    quantity: float = 0.0
    institution_price: Optional[float] = None
    institution_value: Optional[float] = None
    cost_basis: Optional[float] = None
    iso_currency_code: Optional[str] = None


class PlaidLiability(BaseModel):
    """A liability (loan/credit) from Plaid."""

    model_config = ConfigDict(frozen=True)

    account_id: str = ""
    type: str = ""
    last_payment_amount: Optional[float] = None
    last_payment_date: Optional[str] = None
    minimum_payment_amount: Optional[float] = None
    next_payment_due_date: Optional[str] = None
    aprs: list[dict[str, Any]] = Field(default_factory=list)


class PlaidProcessorToken(BaseModel):
    """A processor token for third-party integrations."""

    model_config = ConfigDict(frozen=True)

    processor_token: str
    request_id: str = ""
