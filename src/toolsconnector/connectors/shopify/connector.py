"""Shopify connector -- products, orders, and customers.

Uses the Shopify REST Admin API (2024-01) with access token authentication.
Link-header cursor pagination with ``page_info`` parameters.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from ._parsers import parse_customer, parse_link_header, parse_order, parse_product
from .types import ShopifyCustomer, ShopifyOrder, ShopifyProduct

logger = logging.getLogger("toolsconnector.shopify")


class Shopify(BaseConnector):
    """Connect to Shopify to manage products, orders, and customers.

    Supports access token authentication via ``X-Shopify-Access-Token``
    header.  Credentials format: ``access_token:store_name``.
    The store name is used to construct the base URL:
    ``https://{store}.myshopify.com/admin/api/2024-01``.
    """

    name = "shopify"
    display_name = "Shopify"
    category = ConnectorCategory.ECOMMERCE
    protocol = ProtocolType.REST
    base_url = "https://{store}.myshopify.com/admin/api/2024-01"
    description = (
        "Connect to Shopify to manage products, orders, "
        "and customers via the REST Admin API."
    )
    _rate_limit_config = RateLimitSpec(rate=40, period=1, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Shopify access token.

        Parses credentials as ``access_token:store_name`` to build the
        base URL and set the authentication header.
        """
        creds = self._credentials or ":"
        parts = creds.split(":", 1)
        access_token = parts[0]
        store = parts[1] if len(parts) > 1 else ""

        resolved_url = (
            self._base_url
            or self.__class__.base_url.format(store=store)
        )

        headers: dict[str, str] = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=resolved_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the Shopify Admin API.

        Args:
            method: HTTP method (GET, POST, PUT, etc.).
            path: API path relative to base_url.
            params: Query parameters for GET requests.
            json_body: JSON body for POST/PUT requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json_body,
        )

        call_limit = resp.headers.get("X-Shopify-Shop-Api-Call-Limit")
        if call_limit:
            logger.debug("Shopify rate-limit: %s", call_limit)

        resp.raise_for_status()
        return resp

    def _build_page_state(self, resp: httpx.Response) -> PageState:
        """Build a PageState from Shopify Link header.

        Args:
            resp: The httpx response containing Link headers.

        Returns:
            PageState with cursor set to the next page_info if available.
        """
        links = parse_link_header(resp.headers.get("link"))
        next_cursor = links.get("next")
        return PageState(has_more=bool(next_cursor), cursor=next_cursor)

    # ------------------------------------------------------------------
    # Actions -- Products
    # ------------------------------------------------------------------

    @action("List products from your Shopify store")
    async def list_products(
        self,
        limit: int = 50,
        since_id: Optional[int] = None,
    ) -> PaginatedList[ShopifyProduct]:
        """List products with Link header pagination.

        Args:
            limit: Maximum number of products to return (1-250).
            since_id: Only return products after this ID.

        Returns:
            Paginated list of ShopifyProduct objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 250)}
        if since_id is not None:
            params["since_id"] = since_id

        resp = await self._request("GET", "/products.json", params=params)
        body = resp.json()

        items = [parse_product(p) for p in body.get("products", [])]
        page_state = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=page_state)
        result._fetch_next = (
            (lambda: self._list_products_cursor(limit, page_state.cursor))
            if page_state.has_more else None
        )
        return result

    async def _list_products_cursor(
        self, limit: int, page_info: Optional[str],
    ) -> PaginatedList[ShopifyProduct]:
        """Fetch the next page of products using page_info cursor.

        Args:
            limit: Page size.
            page_info: Cursor from the previous Link header.

        Returns:
            Next paginated list of ShopifyProduct objects.
        """
        params: dict[str, Any] = {"limit": limit, "page_info": page_info}
        resp = await self._request("GET", "/products.json", params=params)
        body = resp.json()

        items = [parse_product(p) for p in body.get("products", [])]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        result._fetch_next = (
            (lambda: self._list_products_cursor(limit, ps.cursor))
            if ps.has_more else None
        )
        return result

    @action("Get a single Shopify product by ID")
    async def get_product(self, product_id: int) -> ShopifyProduct:
        """Retrieve a single product by its ID.

        Args:
            product_id: The Shopify product ID.

        Returns:
            ShopifyProduct object.
        """
        resp = await self._request("GET", f"/products/{product_id}.json")
        return parse_product(resp.json()["product"])

    @action("Create a new product in your Shopify store", dangerous=True)
    async def create_product(
        self,
        title: str,
        body_html: Optional[str] = None,
        vendor: Optional[str] = None,
        product_type: Optional[str] = None,
        variants: Optional[list[dict[str, Any]]] = None,
    ) -> ShopifyProduct:
        """Create a new product in Shopify.

        Args:
            title: Product title.
            body_html: HTML description of the product.
            vendor: Product vendor name.
            product_type: Product type/category.
            variants: List of variant dicts (price, sku, etc.).

        Returns:
            The created ShopifyProduct object.
        """
        product_data: dict[str, Any] = {"title": title}
        if body_html is not None:
            product_data["body_html"] = body_html
        if vendor is not None:
            product_data["vendor"] = vendor
        if product_type is not None:
            product_data["product_type"] = product_type
        if variants is not None:
            product_data["variants"] = variants

        resp = await self._request(
            "PUT", "/products.json",
            json_body={"product": product_data},
        )
        return parse_product(resp.json()["product"])

    @action("Update an existing Shopify product", dangerous=True)
    async def update_product(
        self,
        product_id: int,
        title: Optional[str] = None,
        body_html: Optional[str] = None,
    ) -> ShopifyProduct:
        """Update an existing product.

        Args:
            product_id: The Shopify product ID.
            title: New product title.
            body_html: New HTML description.

        Returns:
            The updated ShopifyProduct object.
        """
        product_data: dict[str, Any] = {"id": product_id}
        if title is not None:
            product_data["title"] = title
        if body_html is not None:
            product_data["body_html"] = body_html

        resp = await self._request(
            "PUT", f"/products/{product_id}.json",
            json_body={"product": product_data},
        )
        return parse_product(resp.json()["product"])

    # ------------------------------------------------------------------
    # Actions -- Orders
    # ------------------------------------------------------------------

    @action("List orders from your Shopify store")
    async def list_orders(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        since_id: Optional[int] = None,
    ) -> PaginatedList[ShopifyOrder]:
        """List orders with optional status filter.

        Args:
            status: Filter by status (open, closed, cancelled, any).
            limit: Maximum number of orders to return (1-250).
            since_id: Only return orders after this ID.

        Returns:
            Paginated list of ShopifyOrder objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 250)}
        if status is not None:
            params["status"] = status
        if since_id is not None:
            params["since_id"] = since_id

        resp = await self._request("GET", "/orders.json", params=params)
        body = resp.json()

        items = [parse_order(o) for o in body.get("orders", [])]
        page_state = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=page_state)
        result._fetch_next = (
            (lambda: self._list_orders_cursor(status, limit, page_state.cursor))
            if page_state.has_more else None
        )
        return result

    async def _list_orders_cursor(
        self, status: Optional[str], limit: int, page_info: Optional[str],
    ) -> PaginatedList[ShopifyOrder]:
        """Fetch next page of orders via cursor.

        Args:
            status: Status filter (carried forward).
            limit: Page size.
            page_info: Cursor from previous Link header.

        Returns:
            Next paginated list of ShopifyOrder objects.
        """
        params: dict[str, Any] = {"limit": limit, "page_info": page_info}
        if status is not None:
            params["status"] = status

        resp = await self._request("GET", "/orders.json", params=params)
        body = resp.json()

        items = [parse_order(o) for o in body.get("orders", [])]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        result._fetch_next = (
            (lambda: self._list_orders_cursor(status, limit, ps.cursor))
            if ps.has_more else None
        )
        return result

    @action("Get a single Shopify order by ID")
    async def get_order(self, order_id: int) -> ShopifyOrder:
        """Retrieve a single order by its ID.

        Args:
            order_id: The Shopify order ID.

        Returns:
            ShopifyOrder object.
        """
        resp = await self._request("GET", f"/orders/{order_id}.json")
        return parse_order(resp.json()["order"])

    # ------------------------------------------------------------------
    # Actions -- Customers
    # ------------------------------------------------------------------

    @action("List customers from your Shopify store")
    async def list_customers(
        self,
        limit: int = 50,
        since_id: Optional[int] = None,
    ) -> PaginatedList[ShopifyCustomer]:
        """List customers with Link header pagination.

        Args:
            limit: Maximum number of customers to return (1-250).
            since_id: Only return customers after this ID.

        Returns:
            Paginated list of ShopifyCustomer objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 250)}
        if since_id is not None:
            params["since_id"] = since_id

        resp = await self._request("GET", "/customers.json", params=params)
        body = resp.json()

        items = [parse_customer(c) for c in body.get("customers", [])]
        page_state = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=page_state)
        result._fetch_next = (
            (lambda: self._list_customers_cursor(limit, page_state.cursor))
            if page_state.has_more else None
        )
        return result

    async def _list_customers_cursor(
        self, limit: int, page_info: Optional[str],
    ) -> PaginatedList[ShopifyCustomer]:
        """Fetch next page of customers via cursor.

        Args:
            limit: Page size.
            page_info: Cursor from previous Link header.

        Returns:
            Next paginated list of ShopifyCustomer objects.
        """
        params: dict[str, Any] = {"limit": limit, "page_info": page_info}
        resp = await self._request("GET", "/customers.json", params=params)
        body = resp.json()

        items = [parse_customer(c) for c in body.get("customers", [])]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        result._fetch_next = (
            (lambda: self._list_customers_cursor(limit, ps.cursor))
            if ps.has_more else None
        )
        return result

    @action("Get a single Shopify customer by ID")
    async def get_customer(self, customer_id: int) -> ShopifyCustomer:
        """Retrieve a single customer by their ID.

        Args:
            customer_id: The Shopify customer ID.

        Returns:
            ShopifyCustomer object.
        """
        resp = await self._request("GET", f"/customers/{customer_id}.json")
        return parse_customer(resp.json()["customer"])

    # ------------------------------------------------------------------
    # Actions -- Order management (extended)
    # ------------------------------------------------------------------

    @action("Update an existing order")
    async def update_order(
        self,
        order_id: int,
        note: Optional[str] = None,
    ) -> ShopifyOrder:
        """Update an order's properties.

        Args:
            order_id: The Shopify order ID.
            note: New note for the order.

        Returns:
            The updated ShopifyOrder.
        """
        order_data: dict[str, Any] = {"id": order_id}
        if note is not None:
            order_data["note"] = note
        resp = await self._request(
            "PUT", f"/orders/{order_id}.json",
            json_body={"order": order_data},
        )
        return parse_order(resp.json()["order"])

    @action("Cancel an order", dangerous=True)
    async def cancel_order(self, order_id: int) -> ShopifyOrder:
        """Cancel an open order.

        Args:
            order_id: The Shopify order ID.

        Returns:
            The cancelled ShopifyOrder.
        """
        resp = await self._request(
            "POST", f"/orders/{order_id}/cancel.json",
        )
        return parse_order(resp.json()["order"])

    # ------------------------------------------------------------------
    # Actions -- Discounts
    # ------------------------------------------------------------------

    @action("Create a price rule / discount", dangerous=True)
    async def create_discount(
        self,
        title: str,
        value: str,
        type: str,
    ) -> dict[str, Any]:
        """Create a discount price rule.

        Args:
            title: The discount title.
            value: The discount value (e.g. ``"-10.0"`` for 10 off).
            type: Value type (``"percentage"`` or ``"fixed_amount"``).

        Returns:
            Dict with the created price rule data.
        """
        payload: dict[str, Any] = {
            "price_rule": {
                "title": title,
                "target_type": "line_item",
                "target_selection": "all",
                "allocation_method": "across",
                "value_type": type,
                "value": value,
                "customer_selection": "all",
                "starts_at": "2020-01-01T00:00:00Z",
            },
        }
        resp = await self._request(
            "POST", "/price_rules.json", json_body=payload,
        )
        return resp.json().get("price_rule", {})

    # ------------------------------------------------------------------
    # Actions -- Collections
    # ------------------------------------------------------------------

    @action("List collections from your Shopify store")
    async def list_collections(
        self, limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """List custom collections.

        Args:
            limit: Maximum number of collections to return.

        Returns:
            List of collection dicts.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = min(limit, 250)
        resp = await self._request(
            "GET", "/custom_collections.json", params=params or None,
        )
        return resp.json().get("custom_collections", [])

    # ------------------------------------------------------------------
    # Actions -- Inventory
    # ------------------------------------------------------------------

    @action("List inventory levels by location")
    async def list_inventory_levels(
        self, location_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """List inventory levels, optionally filtered by location.

        Args:
            location_id: Optional location ID to filter by.

        Returns:
            List of inventory level dicts.
        """
        params: dict[str, Any] = {}
        if location_id is not None:
            params["location_ids"] = location_id
        resp = await self._request(
            "GET", "/inventory_levels.json", params=params or None,
        )
        return resp.json().get("inventory_levels", [])

    # ------------------------------------------------------------------
    # Actions -- Customer management (extended)
    # ------------------------------------------------------------------

    @action("Create a new customer", dangerous=True)
    async def create_customer(
        self,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> ShopifyCustomer:
        """Create a new customer in the Shopify store.

        Args:
            email: Customer email address (required).
            first_name: Customer's first name.
            last_name: Customer's last name.

        Returns:
            The created ShopifyCustomer object.
        """
        customer_data: dict[str, Any] = {"email": email}
        if first_name is not None:
            customer_data["first_name"] = first_name
        if last_name is not None:
            customer_data["last_name"] = last_name

        resp = await self._request(
            "POST", "/customers.json",
            json_body={"customer": customer_data},
        )
        return parse_customer(resp.json()["customer"])

    # ------------------------------------------------------------------
    # Actions -- Fulfillments
    # ------------------------------------------------------------------

    @action("List fulfillments for an order")
    async def list_fulfillments(
        self, order_id: int,
    ) -> list[dict[str, Any]]:
        """List all fulfillments for a specific order.

        Args:
            order_id: The Shopify order ID.

        Returns:
            List of fulfillment dicts with tracking info and line items.
        """
        resp = await self._request(
            "GET", f"/orders/{order_id}/fulfillments.json",
        )
        return resp.json().get("fulfillments", [])

    @action("Fulfill an order", dangerous=True)
    async def fulfill_order(
        self,
        order_id: int,
        tracking_number: Optional[str] = None,
        tracking_company: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a fulfillment for an order.

        This marks the order (or part of it) as fulfilled and
        optionally adds tracking information.

        Args:
            order_id: The Shopify order ID to fulfill.
            tracking_number: Optional shipment tracking number.
            tracking_company: Optional shipping carrier name.

        Returns:
            Dict with the created fulfillment details.
        """
        fulfillment_data: dict[str, Any] = {
            "notify_customer": True,
        }
        if tracking_number is not None:
            fulfillment_data["tracking_number"] = tracking_number
        if tracking_company is not None:
            fulfillment_data["tracking_company"] = tracking_company

        resp = await self._request(
            "POST", f"/orders/{order_id}/fulfillments.json",
            json_body={"fulfillment": fulfillment_data},
        )
        return resp.json().get("fulfillment", {})

    @action("Update inventory quantity for an item")
    async def update_inventory(
        self,
        inventory_item_id: int,
        available: int,
    ) -> dict[str, Any]:
        """Set the available inventory for an item at a location.

        Args:
            inventory_item_id: The inventory item ID.
            available: The new available quantity.

        Returns:
            Dict with the updated inventory level data.
        """
        payload: dict[str, Any] = {
            "inventory_item_id": inventory_item_id,
            "available": available,
        }
        resp = await self._request(
            "POST", "/inventory_levels/set.json", json_body=payload,
        )
        return resp.json().get("inventory_level", {})
