"""Pydantic models for Shopify connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class ShopifyAddress(BaseModel):
    """A Shopify mailing address."""

    model_config = ConfigDict(frozen=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    country: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    province_code: Optional[str] = None
    country_code: Optional[str] = None


class ShopifyVariant(BaseModel):
    """A Shopify product variant."""

    model_config = ConfigDict(frozen=True)

    id: int
    product_id: Optional[int] = None
    title: Optional[str] = None
    price: Optional[str] = None
    sku: Optional[str] = None
    position: Optional[int] = None
    inventory_quantity: Optional[int] = None
    compare_at_price: Optional[str] = None
    option1: Optional[str] = None
    option2: Optional[str] = None
    option3: Optional[str] = None
    taxable: bool = True
    barcode: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ShopifyLineItem(BaseModel):
    """A line item in a Shopify order."""

    model_config = ConfigDict(frozen=True)

    id: int
    variant_id: Optional[int] = None
    product_id: Optional[int] = None
    title: Optional[str] = None
    quantity: int = 0
    price: Optional[str] = None
    sku: Optional[str] = None
    variant_title: Optional[str] = None
    vendor: Optional[str] = None
    name: Optional[str] = None
    taxable: bool = True
    total_discount: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class ShopifyProduct(BaseModel):
    """A Shopify product."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: Optional[str] = None
    body_html: Optional[str] = None
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    handle: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[str] = None
    variants: list[ShopifyVariant] = Field(default_factory=list)
    published_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ShopifyOrder(BaseModel):
    """A Shopify order."""

    model_config = ConfigDict(frozen=True)

    id: int
    order_number: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    financial_status: Optional[str] = None
    fulfillment_status: Optional[str] = None
    total_price: Optional[str] = None
    subtotal_price: Optional[str] = None
    total_tax: Optional[str] = None
    total_discounts: Optional[str] = None
    currency: Optional[str] = None
    line_items: list[ShopifyLineItem] = Field(default_factory=list)
    shipping_address: Optional[ShopifyAddress] = None
    billing_address: Optional[ShopifyAddress] = None
    customer_id: Optional[int] = None
    note: Optional[str] = None
    tags: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    cancelled_at: Optional[str] = None


class ShopifyCustomer(BaseModel):
    """A Shopify customer."""

    model_config = ConfigDict(frozen=True)

    id: int
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    orders_count: int = 0
    total_spent: Optional[str] = None
    state: Optional[str] = None
    verified_email: bool = False
    tags: Optional[str] = None
    default_address: Optional[ShopifyAddress] = None
    note: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ShopifyDraftOrder(BaseModel):
    """A Shopify draft order."""

    model_config = ConfigDict(frozen=True)

    id: int
    order_id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None
    total_price: Optional[str] = None
    subtotal_price: Optional[str] = None
    total_tax: Optional[str] = None
    currency: Optional[str] = None
    line_items: list[ShopifyLineItem] = Field(default_factory=list)
    shipping_address: Optional[ShopifyAddress] = None
    billing_address: Optional[ShopifyAddress] = None
    customer_id: Optional[int] = None
    tags: Optional[str] = None
    invoice_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None


class ShopifyWebhook(BaseModel):
    """A Shopify webhook subscription."""

    model_config = ConfigDict(frozen=True)

    id: int
    topic: Optional[str] = None
    address: Optional[str] = None
    format: Optional[str] = None
    fields: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ShopifyLocation(BaseModel):
    """A Shopify location."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    province_code: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    active: Optional[bool] = None
    legacy: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
