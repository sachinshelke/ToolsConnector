"""Shopify connector -- products, orders, customers, and more."""

from __future__ import annotations

from .connector import Shopify
from .types import (
    ShopifyAddress,
    ShopifyCustomer,
    ShopifyDraftOrder,
    ShopifyLineItem,
    ShopifyLocation,
    ShopifyOrder,
    ShopifyProduct,
    ShopifyVariant,
    ShopifyWebhook,
)

__all__ = [
    "Shopify",
    "ShopifyAddress",
    "ShopifyCustomer",
    "ShopifyDraftOrder",
    "ShopifyLineItem",
    "ShopifyLocation",
    "ShopifyOrder",
    "ShopifyProduct",
    "ShopifyVariant",
    "ShopifyWebhook",
]
