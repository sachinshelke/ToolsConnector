"""Shopify API response parsers.

Helper functions to parse raw JSON dicts from the Shopify REST Admin API
into typed Pydantic models. Also includes Link header parsing for cursor
pagination.
"""

from __future__ import annotations

import re
from typing import Any, Optional

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

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="(\w+)"')
_PAGE_INFO_RE = re.compile(r'[?&]page_info=([^&>]+)')


def parse_link_header(header: Optional[str]) -> dict[str, str]:
    """Parse a Shopify ``Link`` header into a dict of rel -> page_info.

    Shopify uses cursor-based pagination via Link headers with
    ``page_info`` query parameters.

    Args:
        header: Raw Link header value.

    Returns:
        Dict mapping rel names (``next``, ``previous``) to page_info cursors.
    """
    if not header:
        return {}
    result: dict[str, str] = {}
    for url, rel in _LINK_RE.findall(header):
        match = _PAGE_INFO_RE.search(url)
        if match:
            result[rel] = match.group(1)
    return result


def _parse_address(data: Optional[dict[str, Any]]) -> Optional[ShopifyAddress]:
    """Parse a Shopify address dict into a ShopifyAddress.

    Args:
        data: Raw address dict or None.

    Returns:
        ShopifyAddress instance or None.
    """
    if not data:
        return None
    return ShopifyAddress(
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        company=data.get("company"),
        address1=data.get("address1"),
        address2=data.get("address2"),
        city=data.get("city"),
        province=data.get("province"),
        country=data.get("country"),
        zip=data.get("zip"),
        phone=data.get("phone"),
        province_code=data.get("province_code"),
        country_code=data.get("country_code"),
    )


def parse_variant(data: dict[str, Any]) -> ShopifyVariant:
    """Parse a ShopifyVariant from API JSON.

    Args:
        data: Raw JSON dict from the Shopify API.

    Returns:
        A ShopifyVariant instance.
    """
    return ShopifyVariant(
        id=data["id"],
        product_id=data.get("product_id"),
        title=data.get("title"),
        price=data.get("price"),
        sku=data.get("sku"),
        position=data.get("position"),
        inventory_quantity=data.get("inventory_quantity"),
        compare_at_price=data.get("compare_at_price"),
        option1=data.get("option1"),
        option2=data.get("option2"),
        option3=data.get("option3"),
        taxable=data.get("taxable", True),
        barcode=data.get("barcode"),
        weight=data.get("weight"),
        weight_unit=data.get("weight_unit"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def parse_line_item(data: dict[str, Any]) -> ShopifyLineItem:
    """Parse a ShopifyLineItem from API JSON.

    Args:
        data: Raw JSON dict for a line item.

    Returns:
        A ShopifyLineItem instance.
    """
    return ShopifyLineItem(
        id=data["id"],
        variant_id=data.get("variant_id"),
        product_id=data.get("product_id"),
        title=data.get("title"),
        quantity=data.get("quantity", 0),
        price=data.get("price"),
        sku=data.get("sku"),
        variant_title=data.get("variant_title"),
        vendor=data.get("vendor"),
        name=data.get("name"),
        taxable=data.get("taxable", True),
        total_discount=data.get("total_discount"),
    )


def parse_product(data: dict[str, Any]) -> ShopifyProduct:
    """Parse a ShopifyProduct from API JSON.

    Args:
        data: Raw JSON dict from the Shopify API.

    Returns:
        A ShopifyProduct instance.
    """
    variants_raw = data.get("variants") or []
    return ShopifyProduct(
        id=data["id"],
        title=data.get("title"),
        body_html=data.get("body_html"),
        vendor=data.get("vendor"),
        product_type=data.get("product_type"),
        handle=data.get("handle"),
        status=data.get("status"),
        tags=data.get("tags"),
        variants=[parse_variant(v) for v in variants_raw],
        published_at=data.get("published_at"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def parse_order(data: dict[str, Any]) -> ShopifyOrder:
    """Parse a ShopifyOrder from API JSON.

    Args:
        data: Raw JSON dict from the Shopify API.

    Returns:
        A ShopifyOrder instance.
    """
    line_items_raw = data.get("line_items") or []
    customer = data.get("customer") or {}
    return ShopifyOrder(
        id=data["id"],
        order_number=data.get("order_number"),
        name=data.get("name"),
        email=data.get("email"),
        financial_status=data.get("financial_status"),
        fulfillment_status=data.get("fulfillment_status"),
        total_price=data.get("total_price"),
        subtotal_price=data.get("subtotal_price"),
        total_tax=data.get("total_tax"),
        total_discounts=data.get("total_discounts"),
        currency=data.get("currency"),
        line_items=[parse_line_item(li) for li in line_items_raw],
        shipping_address=_parse_address(data.get("shipping_address")),
        billing_address=_parse_address(data.get("billing_address")),
        customer_id=customer.get("id"),
        note=data.get("note"),
        tags=data.get("tags"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        closed_at=data.get("closed_at"),
        cancelled_at=data.get("cancelled_at"),
    )


def parse_customer(data: dict[str, Any]) -> ShopifyCustomer:
    """Parse a ShopifyCustomer from API JSON.

    Args:
        data: Raw JSON dict from the Shopify API.

    Returns:
        A ShopifyCustomer instance.
    """
    return ShopifyCustomer(
        id=data["id"],
        email=data.get("email"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        phone=data.get("phone"),
        orders_count=data.get("orders_count", 0),
        total_spent=data.get("total_spent"),
        state=data.get("state"),
        verified_email=data.get("verified_email", False),
        tags=data.get("tags"),
        default_address=_parse_address(data.get("default_address")),
        note=data.get("note"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def parse_draft_order(data: dict[str, Any]) -> ShopifyDraftOrder:
    """Parse a ShopifyDraftOrder from API JSON.

    Args:
        data: Raw JSON dict from the Shopify API.

    Returns:
        A ShopifyDraftOrder instance.
    """
    line_items_raw = data.get("line_items") or []
    customer = data.get("customer") or {}
    return ShopifyDraftOrder(
        id=data["id"],
        order_id=data.get("order_id"),
        name=data.get("name"),
        email=data.get("email"),
        status=data.get("status"),
        note=data.get("note"),
        total_price=data.get("total_price"),
        subtotal_price=data.get("subtotal_price"),
        total_tax=data.get("total_tax"),
        currency=data.get("currency"),
        line_items=[parse_line_item(li) for li in line_items_raw],
        shipping_address=_parse_address(data.get("shipping_address")),
        billing_address=_parse_address(data.get("billing_address")),
        customer_id=customer.get("id"),
        tags=data.get("tags"),
        invoice_url=data.get("invoice_url"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        completed_at=data.get("completed_at"),
    )


def parse_webhook(data: dict[str, Any]) -> ShopifyWebhook:
    """Parse a ShopifyWebhook from API JSON.

    Args:
        data: Raw JSON dict from the Shopify API.

    Returns:
        A ShopifyWebhook instance.
    """
    return ShopifyWebhook(
        id=data["id"],
        topic=data.get("topic"),
        address=data.get("address"),
        format=data.get("format"),
        fields=data.get("fields") or [],
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def parse_location(data: dict[str, Any]) -> ShopifyLocation:
    """Parse a ShopifyLocation from API JSON.

    Args:
        data: Raw JSON dict from the Shopify API.

    Returns:
        A ShopifyLocation instance.
    """
    return ShopifyLocation(
        id=data["id"],
        name=data.get("name"),
        address1=data.get("address1"),
        address2=data.get("address2"),
        city=data.get("city"),
        province=data.get("province"),
        province_code=data.get("province_code"),
        country=data.get("country"),
        country_code=data.get("country_code"),
        zip=data.get("zip"),
        phone=data.get("phone"),
        active=data.get("active"),
        legacy=data.get("legacy"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )
