"""Stripe connector — customers, charges, payment intents, invoices, and balance.

Uses the Stripe REST API v1 with API key authentication (Basic auth).
Stripe requires form-encoded request bodies (application/x-www-form-urlencoded),
NOT JSON. Cursor-based pagination via ``starting_after`` parameter.
"""

from __future__ import annotations

import base64
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

from ._parsers import (
    flatten_metadata,
    parse_charge,
    parse_customer,
    parse_invoice,
    parse_payment_intent,
)
from .types import (
    PaymentIntent,
    StripeBalance,
    StripeBalanceAvailable,
    StripeBalancePending,
    StripeCharge,
    StripeCustomer,
    StripeInvoice,
)

logger = logging.getLogger("toolsconnector.stripe")


class Stripe(BaseConnector):
    """Connect to Stripe to manage customers, charges, payment intents, and invoices.

    Supports API key authentication via HTTP Basic auth (key as username,
    empty password). All write requests use ``application/x-www-form-urlencoded``
    encoding as required by the Stripe API.
    """

    name = "stripe"
    display_name = "Stripe"
    category = ConnectorCategory.FINANCE
    protocol = ProtocolType.REST
    base_url = "https://api.stripe.com/v1"
    description = (
        "Connect to Stripe to manage customers, charges, "
        "payment intents, invoices, and account balance."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=1, burst=25)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Basic auth.

        Stripe authenticates via HTTP Basic auth using the API key as the
        username and an empty string as the password.
        """
        api_key = self._credentials or ""
        token = base64.b64encode(f"{api_key}:".encode()).decode()

        headers: dict[str, str] = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
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
        data: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        """Send an authenticated request with form-encoded body.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to base_url.
            params: Query parameters for GET requests.
            data: Form-encoded body for POST/PUT requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, data=data,
        )

        remaining = resp.headers.get("RateLimit-Remaining")
        if remaining is not None:
            logger.debug("Stripe rate-limit remaining: %s", remaining)

        resp.raise_for_status()
        return resp

    def _build_page_state(self, data: dict[str, Any]) -> PageState:
        """Build a PageState from Stripe list response.

        Args:
            data: Parsed JSON response body from a Stripe list endpoint.

        Returns:
            PageState with cursor set to the last item ID if more exist.
        """
        has_more = data.get("has_more", False)
        items = data.get("data", [])
        cursor = items[-1]["id"] if has_more and items else None
        return PageState(has_more=has_more, cursor=cursor)

    # ------------------------------------------------------------------
    # Actions — Customers
    # ------------------------------------------------------------------

    @action("List customers from your Stripe account")
    async def list_customers(
        self,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripeCustomer]:
        """List customers with cursor-based pagination.

        Args:
            limit: Maximum number of customers to return (1-100).
            starting_after: Customer ID to paginate after (cursor).

        Returns:
            Paginated list of StripeCustomer objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/customers", params=params)
        body = resp.json()

        items = [parse_customer(c) for c in body.get("data", [])]
        page_state = self._build_page_state(body)

        result = PaginatedList(
            items=items, page_state=page_state,
            total_count=body.get("total_count"),
        )
        result._fetch_next = (
            (lambda cursor=page_state.cursor: self.alist_customers(
                limit=limit, starting_after=cursor,
            ))
            if page_state.has_more else None
        )
        return result

    @action("Retrieve a single Stripe customer by ID")
    async def get_customer(self, customer_id: str) -> StripeCustomer:
        """Retrieve a single customer.

        Args:
            customer_id: The Stripe customer ID (e.g. ``cus_...``).

        Returns:
            StripeCustomer object.
        """
        resp = await self._request("GET", f"/customers/{customer_id}")
        return parse_customer(resp.json())

    @action("Create a new Stripe customer", dangerous=True)
    async def create_customer(
        self,
        email: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> StripeCustomer:
        """Create a new customer in Stripe.

        Args:
            email: Customer email address.
            name: Customer full name.
            description: Arbitrary description for the customer.
            metadata: Key-value metadata to attach to the customer.

        Returns:
            The created StripeCustomer object.
        """
        form_data: dict[str, Any] = {}
        if email is not None:
            form_data["email"] = email
        if name is not None:
            form_data["name"] = name
        if description is not None:
            form_data["description"] = description
        if metadata:
            form_data.update(flatten_metadata(metadata))

        resp = await self._request("POST", "/customers", data=form_data)
        return parse_customer(resp.json())

    # ------------------------------------------------------------------
    # Actions — Charges
    # ------------------------------------------------------------------

    @action("List charges from your Stripe account")
    async def list_charges(
        self,
        customer: Optional[str] = None,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripeCharge]:
        """List charges with optional customer filter and cursor pagination.

        Args:
            customer: Filter charges by customer ID.
            limit: Maximum number of charges to return (1-100).
            starting_after: Charge ID to paginate after (cursor).

        Returns:
            Paginated list of StripeCharge objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if customer:
            params["customer"] = customer
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/charges", params=params)
        body = resp.json()

        items = [parse_charge(c) for c in body.get("data", [])]
        page_state = self._build_page_state(body)

        result = PaginatedList(
            items=items, page_state=page_state,
            total_count=body.get("total_count"),
        )
        result._fetch_next = (
            (lambda cursor=page_state.cursor: self.alist_charges(
                customer=customer, limit=limit, starting_after=cursor,
            ))
            if page_state.has_more else None
        )
        return result

    @action("Retrieve a single Stripe charge by ID")
    async def get_charge(self, charge_id: str) -> StripeCharge:
        """Retrieve a single charge.

        Args:
            charge_id: The Stripe charge ID (e.g. ``ch_...``).

        Returns:
            StripeCharge object.
        """
        resp = await self._request("GET", f"/charges/{charge_id}")
        return parse_charge(resp.json())

    # ------------------------------------------------------------------
    # Actions — Payment Intents
    # ------------------------------------------------------------------

    @action("Create a Stripe PaymentIntent", dangerous=True)
    async def create_payment_intent(
        self,
        amount: int,
        currency: str,
        customer: Optional[str] = None,
        description: Optional[str] = None,
    ) -> PaymentIntent:
        """Create a new PaymentIntent for a payment flow.

        Args:
            amount: Amount in the smallest currency unit (e.g. cents).
            currency: Three-letter ISO currency code (e.g. ``usd``).
            customer: Optional customer ID to associate with the intent.
            description: Arbitrary description for the payment.

        Returns:
            The created PaymentIntent object.
        """
        form_data: dict[str, Any] = {
            "amount": str(amount),
            "currency": currency,
        }
        if customer is not None:
            form_data["customer"] = customer
        if description is not None:
            form_data["description"] = description

        resp = await self._request("POST", "/payment_intents", data=form_data)
        return parse_payment_intent(resp.json())

    # ------------------------------------------------------------------
    # Actions — Invoices
    # ------------------------------------------------------------------

    @action("List invoices from your Stripe account")
    async def list_invoices(
        self,
        customer: Optional[str] = None,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripeInvoice]:
        """List invoices with optional customer filter and cursor pagination.

        Args:
            customer: Filter invoices by customer ID.
            limit: Maximum number of invoices to return (1-100).
            starting_after: Invoice ID to paginate after (cursor).

        Returns:
            Paginated list of StripeInvoice objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if customer:
            params["customer"] = customer
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/invoices", params=params)
        body = resp.json()

        items = [parse_invoice(inv) for inv in body.get("data", [])]
        page_state = self._build_page_state(body)

        result = PaginatedList(
            items=items, page_state=page_state,
            total_count=body.get("total_count"),
        )
        result._fetch_next = (
            (lambda cursor=page_state.cursor: self.alist_invoices(
                customer=customer, limit=limit, starting_after=cursor,
            ))
            if page_state.has_more else None
        )
        return result

    # ------------------------------------------------------------------
    # Actions — Balance
    # ------------------------------------------------------------------

    @action("Retrieve the current Stripe account balance")
    async def get_balance(self) -> StripeBalance:
        """Retrieve the current balance for your Stripe account.

        Returns:
            StripeBalance with available and pending amounts by currency.
        """
        resp = await self._request("GET", "/balance")
        body = resp.json()

        return StripeBalance(
            object=body.get("object", "balance"),
            available=[
                StripeBalanceAvailable(
                    amount=a.get("amount", 0),
                    currency=a.get("currency", "usd"),
                    source_types=a.get("source_types", {}),
                )
                for a in body.get("available", [])
            ],
            pending=[
                StripeBalancePending(
                    amount=p.get("amount", 0),
                    currency=p.get("currency", "usd"),
                    source_types=p.get("source_types", {}),
                )
                for p in body.get("pending", [])
            ],
            livemode=body.get("livemode", False),
        )
