"""Shopify connector -- products, orders, and customers."""

from __future__ import annotations

from .connector import Shopify
from .types import (
    ShopifyAddress,
    ShopifyCustomer,
    ShopifyLineItem,
    ShopifyOrder,
    ShopifyProduct,
    ShopifyVariant,
)

__all__ = [
    "Shopify",
    "ShopifyAddress",
    "ShopifyCustomer",
    "ShopifyLineItem",
    "ShopifyOrder",
    "ShopifyProduct",
    "ShopifyVariant",
]
