"""Stripe connector — comprehensive API coverage.

Covers customers, charges, payment intents (full lifecycle), invoices,
subscriptions, products, prices, checkout sessions, payment methods,
refunds, disputes, payouts, events, setup intents, and account balance.

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
from toolsconnector.types import PaginatedList

from ._helpers import build_paginated_result
from ._parsers import (
    flatten_metadata,
    parse_charge,
    parse_checkout_session,
    parse_customer,
    parse_dispute,
    parse_event,
    parse_invoice,
    parse_payment_intent,
    parse_payment_method,
    parse_payout,
    parse_price,
    parse_product,
    parse_refund,
    parse_setup_intent,
    parse_subscription,
)
from .types import (
    PaymentIntent,
    StripeBalance,
    StripeBalanceAvailable,
    StripeBalancePending,
    StripeCharge,
    StripeCheckoutSession,
    StripeCustomer,
    StripeDispute,
    StripeEvent,
    StripeInvoice,
    StripePaymentMethod,
    StripePayout,
    StripePrice,
    StripeProduct,
    StripeRefund,
    StripeSetupIntent,
    StripeSubscription,
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
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_customers(
                limit=limit, starting_after=cursor,
            ),
        )

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
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_charges(
                customer=customer, limit=limit, starting_after=cursor,
            ),
        )

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
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_invoices(
                customer=customer, limit=limit, starting_after=cursor,
            ),
        )

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

    # ------------------------------------------------------------------
    # Actions — Customers (continued)
    # ------------------------------------------------------------------

    @action("Update a Stripe customer", dangerous=True)
    async def update_customer(
        self,
        customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> StripeCustomer:
        """Update an existing Stripe customer.

        Args:
            customer_id: The Stripe customer ID (e.g. ``cus_...``).
            email: New email address for the customer.
            name: New name for the customer.
            description: New description for the customer.
            metadata: Key-value metadata to set on the customer.

        Returns:
            The updated StripeCustomer object.
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

        resp = await self._request("POST", f"/customers/{customer_id}", data=form_data)
        return parse_customer(resp.json())

    @action("Delete a Stripe customer", dangerous=True)
    async def delete_customer(self, customer_id: str) -> None:
        """Permanently delete a customer from Stripe.

        Args:
            customer_id: The Stripe customer ID (e.g. ``cus_...``).

        Warning:
            This permanently deletes the customer and cannot be undone.
            Active subscriptions will be cancelled.
        """
        await self._request("DELETE", f"/customers/{customer_id}")

    # ------------------------------------------------------------------
    # Actions — Charges (create)
    # ------------------------------------------------------------------

    @action("Create a charge", dangerous=True)
    async def create_charge(
        self,
        amount: int,
        currency: str,
        customer: Optional[str] = None,
        source: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> StripeCharge:
        """Create a new charge.

        Args:
            amount: Amount in the smallest currency unit (e.g. cents).
            currency: Three-letter ISO currency code (e.g. ``usd``).
            customer: Customer ID to charge.
            source: Payment source token or ID.
            description: Arbitrary description for the charge.
            metadata: Key-value metadata to attach.

        Returns:
            The created StripeCharge object.
        """
        form_data: dict[str, Any] = {
            "amount": str(amount),
            "currency": currency,
        }
        if customer is not None:
            form_data["customer"] = customer
        if source is not None:
            form_data["source"] = source
        if description is not None:
            form_data["description"] = description
        if metadata:
            form_data.update(flatten_metadata(metadata))

        resp = await self._request("POST", "/charges", data=form_data)
        return parse_charge(resp.json())

    # ------------------------------------------------------------------
    # Actions — Refunds
    # ------------------------------------------------------------------

    @action("Refund a charge", dangerous=True)
    async def refund_charge(
        self,
        charge_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> StripeRefund:
        """Create a refund for a charge.

        Args:
            charge_id: The ID of the charge to refund.
            amount: Amount to refund in cents. Omit for full refund.
            reason: Reason for the refund: ``duplicate``,
                ``fraudulent``, or ``requested_by_customer``.

        Returns:
            The created StripeRefund object.
        """
        form_data: dict[str, Any] = {"charge": charge_id}
        if amount is not None:
            form_data["amount"] = str(amount)
        if reason is not None:
            form_data["reason"] = reason

        resp = await self._request("POST", "/refunds", data=form_data)
        return parse_refund(resp.json())

    @action("List refunds from your Stripe account")
    async def list_refunds(
        self,
        charge: Optional[str] = None,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripeRefund]:
        """List refunds with optional charge filter and cursor pagination.

        Args:
            charge: Filter refunds by charge ID.
            limit: Maximum number of refunds to return (1-100).
            starting_after: Refund ID to paginate after (cursor).

        Returns:
            Paginated list of StripeRefund objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if charge:
            params["charge"] = charge
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/refunds", params=params)
        body = resp.json()

        items = [parse_refund(r) for r in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_refunds(
                charge=charge, limit=limit, starting_after=cursor,
            ),
        )

    # ------------------------------------------------------------------
    # Actions — Subscriptions
    # ------------------------------------------------------------------

    @action("Create a subscription", dangerous=True)
    async def create_subscription(
        self,
        customer: str,
        price: str,
        trial_days: Optional[int] = None,
    ) -> StripeSubscription:
        """Create a new subscription for a customer.

        Args:
            customer: The customer ID to subscribe.
            price: The price ID for the subscription.
            trial_days: Number of days for a free trial period.

        Returns:
            The created StripeSubscription object.
        """
        form_data: dict[str, Any] = {
            "customer": customer,
            "items[0][price]": price,
        }
        if trial_days is not None:
            form_data["trial_period_days"] = str(trial_days)

        resp = await self._request("POST", "/subscriptions", data=form_data)
        return parse_subscription(resp.json())

    @action("Cancel a subscription", dangerous=True)
    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True,
    ) -> StripeSubscription:
        """Cancel an active subscription.

        Args:
            subscription_id: The subscription ID to cancel.
            at_period_end: If True, cancel at end of current billing
                period. If False, cancel immediately.

        Returns:
            The updated StripeSubscription object.

        Warning:
            Immediate cancellation stops billing and access right away.
        """
        if at_period_end:
            form_data: dict[str, Any] = {"cancel_at_period_end": "true"}
            resp = await self._request(
                "POST", f"/subscriptions/{subscription_id}", data=form_data,
            )
        else:
            resp = await self._request(
                "DELETE", f"/subscriptions/{subscription_id}",
            )
        return parse_subscription(resp.json())

    @action("List subscriptions from your Stripe account")
    async def list_subscriptions(
        self,
        customer: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripeSubscription]:
        """List subscriptions with optional filters and cursor pagination.

        Args:
            customer: Filter by customer ID.
            status: Filter by status (e.g. ``active``, ``past_due``,
                ``canceled``, ``all``).
            limit: Maximum number of subscriptions to return (1-100).
            starting_after: Subscription ID to paginate after (cursor).

        Returns:
            Paginated list of StripeSubscription objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if customer:
            params["customer"] = customer
        if status:
            params["status"] = status
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/subscriptions", params=params)
        body = resp.json()

        items = [parse_subscription(s) for s in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_subscriptions(
                customer=customer, status=status, limit=limit,
                starting_after=cursor,
            ),
        )

    @action("Retrieve a single Stripe subscription by ID")
    async def get_subscription(self, subscription_id: str) -> StripeSubscription:
        """Retrieve a single subscription.

        Args:
            subscription_id: The Stripe subscription ID (e.g. ``sub_...``).

        Returns:
            StripeSubscription object.
        """
        resp = await self._request("GET", f"/subscriptions/{subscription_id}")
        return parse_subscription(resp.json())

    # ------------------------------------------------------------------
    # Actions — Products
    # ------------------------------------------------------------------

    @action("Create a Stripe product", dangerous=True)
    async def create_product(
        self,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> StripeProduct:
        """Create a new product in Stripe.

        Args:
            name: Product name.
            description: Product description.
            metadata: Key-value metadata to attach.

        Returns:
            The created StripeProduct object.
        """
        form_data: dict[str, Any] = {"name": name}
        if description is not None:
            form_data["description"] = description
        if metadata:
            form_data.update(flatten_metadata(metadata))

        resp = await self._request("POST", "/products", data=form_data)
        return parse_product(resp.json())

    @action("List products from your Stripe account")
    async def list_products(
        self,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripeProduct]:
        """List products with cursor-based pagination.

        Args:
            limit: Maximum number of products to return (1-100).
            starting_after: Product ID to paginate after (cursor).

        Returns:
            Paginated list of StripeProduct objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/products", params=params)
        body = resp.json()

        items = [parse_product(p) for p in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_products(
                limit=limit, starting_after=cursor,
            ),
        )

    # ------------------------------------------------------------------
    # Actions — Prices
    # ------------------------------------------------------------------

    @action("Create a Stripe price", dangerous=True)
    async def create_price(
        self,
        product: str,
        unit_amount: int,
        currency: str,
        recurring_interval: Optional[str] = None,
    ) -> StripePrice:
        """Create a new price for a product.

        Args:
            product: The product ID to attach this price to.
            unit_amount: Price amount in cents.
            currency: Three-letter ISO currency code (e.g. ``usd``).
            recurring_interval: If set, makes this a recurring price.
                One of ``day``, ``week``, ``month``, or ``year``.

        Returns:
            The created StripePrice object.
        """
        form_data: dict[str, Any] = {
            "product": product,
            "unit_amount": str(unit_amount),
            "currency": currency,
        }
        if recurring_interval is not None:
            form_data["recurring[interval]"] = recurring_interval

        resp = await self._request("POST", "/prices", data=form_data)
        return parse_price(resp.json())

    @action("List prices from your Stripe account")
    async def list_prices(
        self,
        product: Optional[str] = None,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripePrice]:
        """List prices with optional product filter and cursor pagination.

        Args:
            product: Filter prices by product ID.
            limit: Maximum number of prices to return (1-100).
            starting_after: Price ID to paginate after (cursor).

        Returns:
            Paginated list of StripePrice objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if product:
            params["product"] = product
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/prices", params=params)
        body = resp.json()

        items = [parse_price(p) for p in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_prices(
                product=product, limit=limit, starting_after=cursor,
            ),
        )

    # ------------------------------------------------------------------
    # Actions — Checkout Sessions
    # ------------------------------------------------------------------

    @action("Create a Stripe Checkout Session", dangerous=True)
    async def create_checkout_session(
        self,
        line_items: list[dict[str, Any]],
        mode: str,
        success_url: str,
        cancel_url: str,
    ) -> StripeCheckoutSession:
        """Create a new Checkout Session for payment collection.

        Args:
            line_items: List of line item dicts, each with ``price`` (price ID)
                and ``quantity``. Example:
                ``[{"price": "price_xxx", "quantity": 1}]``.
            mode: Checkout mode: ``payment``, ``subscription``, or ``setup``.
            success_url: URL to redirect to after successful payment.
            cancel_url: URL to redirect to if the user cancels.

        Returns:
            The created StripeCheckoutSession with a ``url`` for redirect.
        """
        form_data: dict[str, Any] = {
            "mode": mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        for idx, item in enumerate(line_items):
            form_data[f"line_items[{idx}][price]"] = item["price"]
            form_data[f"line_items[{idx}][quantity]"] = str(item.get("quantity", 1))

        resp = await self._request("POST", "/checkout/sessions", data=form_data)
        return parse_checkout_session(resp.json())

    # ------------------------------------------------------------------
    # Actions — Payment Methods
    # ------------------------------------------------------------------

    @action("List payment methods for a customer")
    async def list_payment_methods(
        self,
        customer: str,
        type: Optional[str] = None,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripePaymentMethod]:
        """List payment methods attached to a customer.

        Args:
            customer: The customer ID to list payment methods for.
            type: Filter by payment method type (e.g. ``card``).
            limit: Maximum number of payment methods to return (1-100).
            starting_after: Payment method ID to paginate after (cursor).

        Returns:
            Paginated list of StripePaymentMethod objects.
        """
        params: dict[str, Any] = {
            "customer": customer,
            "limit": min(limit, 100),
        }
        if type:
            params["type"] = type
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/payment_methods", params=params)
        body = resp.json()

        items = [parse_payment_method(pm) for pm in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_payment_methods(
                customer=customer, type=type, limit=limit,
                starting_after=cursor,
            ),
        )

    # ------------------------------------------------------------------
    # Actions — Invoices (continued)
    # ------------------------------------------------------------------

    @action("Retrieve a single Stripe invoice by ID")
    async def get_invoice(self, invoice_id: str) -> StripeInvoice:
        """Retrieve a single invoice.

        Args:
            invoice_id: The Stripe invoice ID (e.g. ``in_...``).

        Returns:
            StripeInvoice object.
        """
        resp = await self._request("GET", f"/invoices/{invoice_id}")
        return parse_invoice(resp.json())

    @action("Void a Stripe invoice", dangerous=True)
    async def void_invoice(self, invoice_id: str) -> StripeInvoice:
        """Void an open invoice so it can no longer be paid.

        Args:
            invoice_id: The Stripe invoice ID to void.

        Returns:
            The voided StripeInvoice object.

        Warning:
            Voiding an invoice is irreversible. The invoice status
            changes to ``void`` and can no longer be paid.
        """
        resp = await self._request("POST", f"/invoices/{invoice_id}/void")
        return parse_invoice(resp.json())

    # ------------------------------------------------------------------
    # Actions — Payment Intents (lifecycle)
    # ------------------------------------------------------------------

    @action("Retrieve a single Stripe PaymentIntent by ID")
    async def get_payment_intent(
        self, payment_intent_id: str,
    ) -> PaymentIntent:
        """Retrieve a single PaymentIntent.

        Args:
            payment_intent_id: The Stripe PaymentIntent ID
                (e.g. ``pi_...``).

        Returns:
            PaymentIntent object.
        """
        resp = await self._request(
            "GET", f"/payment_intents/{payment_intent_id}",
        )
        return parse_payment_intent(resp.json())

    @action("List PaymentIntents from your Stripe account")
    async def list_payment_intents(
        self,
        customer: Optional[str] = None,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[PaymentIntent]:
        """List PaymentIntents with optional customer filter and cursor pagination.

        Args:
            customer: Filter by customer ID.
            limit: Maximum number of PaymentIntents to return (1-100).
            starting_after: PaymentIntent ID to paginate after (cursor).

        Returns:
            Paginated list of PaymentIntent objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if customer:
            params["customer"] = customer
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/payment_intents", params=params)
        body = resp.json()

        items = [parse_payment_intent(pi) for pi in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_payment_intents(
                customer=customer, limit=limit, starting_after=cursor,
            ),
        )

    @action("Confirm a Stripe PaymentIntent", dangerous=True)
    async def confirm_payment_intent(
        self,
        payment_intent_id: str,
        payment_method: Optional[str] = None,
    ) -> PaymentIntent:
        """Confirm a PaymentIntent to initiate the payment flow.

        Args:
            payment_intent_id: The PaymentIntent ID to confirm.
            payment_method: Optional payment method ID to attach before
                confirming (e.g. ``pm_...``).

        Returns:
            The confirmed PaymentIntent object.

        Warning:
            Confirming a PaymentIntent may immediately charge the
            customer's payment method.
        """
        form_data: dict[str, Any] = {}
        if payment_method is not None:
            form_data["payment_method"] = payment_method

        resp = await self._request(
            "POST",
            f"/payment_intents/{payment_intent_id}/confirm",
            data=form_data,
        )
        return parse_payment_intent(resp.json())

    @action("Cancel a Stripe PaymentIntent")
    async def cancel_payment_intent(
        self, payment_intent_id: str,
    ) -> PaymentIntent:
        """Cancel a PaymentIntent that has not been captured.

        Args:
            payment_intent_id: The PaymentIntent ID to cancel.

        Returns:
            The cancelled PaymentIntent object.
        """
        resp = await self._request(
            "POST", f"/payment_intents/{payment_intent_id}/cancel",
        )
        return parse_payment_intent(resp.json())

    @action("Capture a Stripe PaymentIntent", dangerous=True)
    async def capture_payment_intent(
        self,
        payment_intent_id: str,
        amount_to_capture: Optional[int] = None,
    ) -> PaymentIntent:
        """Capture a PaymentIntent that was previously confirmed with manual capture.

        Args:
            payment_intent_id: The PaymentIntent ID to capture.
            amount_to_capture: Amount to capture in the smallest currency
                unit. Omit to capture the full authorized amount.

        Returns:
            The captured PaymentIntent object.

        Warning:
            Capturing finalises the charge and moves funds from the
            customer's payment method.
        """
        form_data: dict[str, Any] = {}
        if amount_to_capture is not None:
            form_data["amount_to_capture"] = str(amount_to_capture)

        resp = await self._request(
            "POST",
            f"/payment_intents/{payment_intent_id}/capture",
            data=form_data,
        )
        return parse_payment_intent(resp.json())

    # ------------------------------------------------------------------
    # Actions — Disputes
    # ------------------------------------------------------------------

    @action("List disputes from your Stripe account")
    async def list_disputes(
        self,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripeDispute]:
        """List disputes (chargebacks) with cursor-based pagination.

        Args:
            limit: Maximum number of disputes to return (1-100).
            starting_after: Dispute ID to paginate after (cursor).

        Returns:
            Paginated list of StripeDispute objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/disputes", params=params)
        body = resp.json()

        items = [parse_dispute(d) for d in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_disputes(
                limit=limit, starting_after=cursor,
            ),
        )

    @action("Retrieve a single Stripe dispute by ID")
    async def get_dispute(self, dispute_id: str) -> StripeDispute:
        """Retrieve a single dispute.

        Args:
            dispute_id: The Stripe dispute ID (e.g. ``dp_...``).

        Returns:
            StripeDispute object.
        """
        resp = await self._request("GET", f"/disputes/{dispute_id}")
        return parse_dispute(resp.json())

    @action("Close a Stripe dispute", dangerous=True)
    async def close_dispute(self, dispute_id: str) -> StripeDispute:
        """Close a dispute, accepting the chargeback.

        Args:
            dispute_id: The Stripe dispute ID to close.

        Returns:
            The closed StripeDispute object.

        Warning:
            Closing a dispute accepts the chargeback. The disputed
            amount will not be returned to your account.
        """
        resp = await self._request(
            "POST", f"/disputes/{dispute_id}/close",
        )
        return parse_dispute(resp.json())

    # ------------------------------------------------------------------
    # Actions — Payouts
    # ------------------------------------------------------------------

    @action("List payouts from your Stripe account")
    async def list_payouts(
        self,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripePayout]:
        """List payouts with cursor-based pagination.

        Args:
            limit: Maximum number of payouts to return (1-100).
            starting_after: Payout ID to paginate after (cursor).

        Returns:
            Paginated list of StripePayout objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/payouts", params=params)
        body = resp.json()

        items = [parse_payout(p) for p in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_payouts(
                limit=limit, starting_after=cursor,
            ),
        )

    @action("Create a payout to your bank account", dangerous=True)
    async def create_payout(
        self,
        amount: int,
        currency: str,
    ) -> StripePayout:
        """Create a payout to send funds to your bank account.

        Args:
            amount: Amount to pay out in the smallest currency unit
                (e.g. cents).
            currency: Three-letter ISO currency code (e.g. ``usd``).

        Returns:
            The created StripePayout object.

        Warning:
            This initiates a real transfer of funds from your Stripe
            balance to your bank account.
        """
        form_data: dict[str, Any] = {
            "amount": str(amount),
            "currency": currency,
        }

        resp = await self._request("POST", "/payouts", data=form_data)
        return parse_payout(resp.json())

    @action("Retrieve a single Stripe payout by ID")
    async def get_payout(self, payout_id: str) -> StripePayout:
        """Retrieve a single payout.

        Args:
            payout_id: The Stripe payout ID (e.g. ``po_...``).

        Returns:
            StripePayout object.
        """
        resp = await self._request("GET", f"/payouts/{payout_id}")
        return parse_payout(resp.json())

    # ------------------------------------------------------------------
    # Actions — Events
    # ------------------------------------------------------------------

    @action("List events from your Stripe account")
    async def list_events(
        self,
        type: Optional[str] = None,
        limit: int = 10,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[StripeEvent]:
        """List events (webhook events) with optional type filter and cursor pagination.

        Args:
            type: Filter by event type (e.g. ``charge.succeeded``,
                ``invoice.payment_failed``).
            limit: Maximum number of events to return (1-100).
            starting_after: Event ID to paginate after (cursor).

        Returns:
            Paginated list of StripeEvent objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if type:
            params["type"] = type
        if starting_after:
            params["starting_after"] = starting_after

        resp = await self._request("GET", "/events", params=params)
        body = resp.json()

        items = [parse_event(e) for e in body.get("data", [])]
        return build_paginated_result(
            items, body,
            lambda cursor: self.alist_events(
                type=type, limit=limit, starting_after=cursor,
            ),
        )

    @action("Retrieve a single Stripe event by ID")
    async def get_event(self, event_id: str) -> StripeEvent:
        """Retrieve a single event.

        Args:
            event_id: The Stripe event ID (e.g. ``evt_...``).

        Returns:
            StripeEvent object.
        """
        resp = await self._request("GET", f"/events/{event_id}")
        return parse_event(resp.json())

    # ------------------------------------------------------------------
    # Actions — Setup Intents
    # ------------------------------------------------------------------

    @action("Create a Stripe SetupIntent", dangerous=False)
    async def create_setup_intent(
        self,
        customer: Optional[str] = None,
        payment_method_types: Optional[list[str]] = None,
    ) -> StripeSetupIntent:
        """Create a SetupIntent to collect payment method details for future use.

        Args:
            customer: Optional customer ID to attach the payment method to.
            payment_method_types: List of payment method types to accept
                (e.g. ``["card"]``). Defaults to Stripe's automatic
                detection if omitted.

        Returns:
            The created StripeSetupIntent object with a ``client_secret``
            for client-side confirmation.
        """
        form_data: dict[str, Any] = {}
        if customer is not None:
            form_data["customer"] = customer
        if payment_method_types:
            for idx, pmt in enumerate(payment_method_types):
                form_data[f"payment_method_types[{idx}]"] = pmt

        resp = await self._request("POST", "/setup_intents", data=form_data)
        return parse_setup_intent(resp.json())

    @action("Retrieve a single Stripe SetupIntent by ID")
    async def get_setup_intent(
        self, setup_intent_id: str,
    ) -> StripeSetupIntent:
        """Retrieve a single SetupIntent.

        Args:
            setup_intent_id: The Stripe SetupIntent ID
                (e.g. ``seti_...``).

        Returns:
            StripeSetupIntent object.
        """
        resp = await self._request(
            "GET", f"/setup_intents/{setup_intent_id}",
        )
        return parse_setup_intent(resp.json())
