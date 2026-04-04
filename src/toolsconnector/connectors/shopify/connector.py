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
