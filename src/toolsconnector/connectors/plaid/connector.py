"""Plaid connector -- accounts, transactions, and banking data via Plaid API."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import (
    PlaidAccount,
    PlaidBalance,
    PlaidHolding,
    PlaidInstitution,
    PlaidInvestmentTransaction,
    PlaidLiability,
    PlaidLinkToken,
    PlaidProcessorToken,
    PlaidTransaction,
)


class Plaid(BaseConnector):
    """Connect to Plaid to access financial accounts, transactions, and balances.

    Credentials format: ``"client_id:secret"`` -- Plaid authenticates by
    including ``client_id`` and ``secret`` in every JSON request body
    (not in headers).

    The ``base_url`` defaults to Plaid production but can be overridden
    to ``https://sandbox.plaid.com`` for testing.
    """

    name = "plaid"
    display_name = "Plaid"
    category = ConnectorCategory.FINANCE
    protocol = ProtocolType.REST
    base_url = "https://production.plaid.com"
    description = (
        "Connect to Plaid for financial data -- accounts, transactions, "
        "balances, identity, and institution lookup."
    )
    _rate_limit_config = RateLimitSpec(rate=30, period=60, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _parse_credentials(self) -> tuple[str, str]:
        """Extract client_id and secret from credentials string.

        Returns:
            Tuple of (client_id, secret).
        """
        creds = str(self._credentials)
        if ":" not in creds:
            raise ValueError("Plaid credentials must be 'client_id:secret' format")
        client_id, secret = creds.split(":", 1)
        return client_id.strip(), secret.strip()

    async def _setup(self) -> None:
        """Initialise the async HTTP client."""
        self._client_id, self._secret = self._parse_credentials()
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_body(self) -> dict[str, str]:
        """Return the auth fields that Plaid requires in every request body.

        Returns:
            Dict with client_id and secret.
        """
        return {
            "client_id": self._client_id,
            "secret": self._secret,
        }

    async def _request(
        self,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a POST request against the Plaid API.

        Plaid uses POST for all endpoints and passes auth in the body.

        Args:
            path: API path relative to ``base_url``.
            json: JSON request body (auth fields are merged automatically).

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        body: dict[str, Any] = {**self._auth_body()}
        if json:
            body.update(json)

        response = await self._client.post(path, json=body)
        raise_typed_for_status(response, connector=self.name)
        return response.json()

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_account(data: dict[str, Any]) -> PlaidAccount:
        """Parse raw JSON into a PlaidAccount."""
        return PlaidAccount(
            account_id=data.get("account_id", ""),
            name=data.get("name", ""),
            official_name=data.get("official_name"),
            type=data.get("type", ""),
            subtype=data.get("subtype"),
            mask=data.get("mask"),
            balances=data.get("balances"),
            verification_status=data.get("verification_status"),
            persistent_account_id=data.get("persistent_account_id"),
        )

    @staticmethod
    def _parse_transaction(data: dict[str, Any]) -> PlaidTransaction:
        """Parse raw JSON into a PlaidTransaction."""
        return PlaidTransaction(
            transaction_id=data.get("transaction_id", ""),
            account_id=data.get("account_id", ""),
            amount=data.get("amount", 0.0),
            name=data.get("name", ""),
            merchant_name=data.get("merchant_name"),
            date=data.get("date", ""),
            datetime=data.get("datetime"),
            authorized_date=data.get("authorized_date"),
            pending=data.get("pending", False),
            category=data.get("category", []),
            category_id=data.get("category_id"),
            payment_channel=data.get("payment_channel"),
            iso_currency_code=data.get("iso_currency_code"),
            unofficial_currency_code=data.get("unofficial_currency_code"),
            location=data.get("location"),
            payment_meta=data.get("payment_meta"),
            personal_finance_category=data.get("personal_finance_category"),
        )

    @staticmethod
    def _parse_balance(
        data: dict[str, Any],
        account_id: str,
    ) -> PlaidBalance:
        """Parse raw balance JSON into a PlaidBalance."""
        return PlaidBalance(
            account_id=account_id,
            current=data.get("current"),
            available=data.get("available"),
            limit=data.get("limit"),
            iso_currency_code=data.get("iso_currency_code"),
            unofficial_currency_code=data.get("unofficial_currency_code"),
            last_updated_datetime=data.get("last_updated_datetime"),
        )

    @staticmethod
    def _parse_institution(data: dict[str, Any]) -> PlaidInstitution:
        """Parse raw JSON into a PlaidInstitution."""
        return PlaidInstitution(
            institution_id=data.get("institution_id", ""),
            name=data.get("name", ""),
            products=data.get("products", []),
            country_codes=data.get("country_codes", []),
            url=data.get("url"),
            primary_color=data.get("primary_color"),
            logo=data.get("logo"),
            routing_numbers=data.get("routing_numbers", []),
            oauth=data.get("oauth", False),
        )

    # ------------------------------------------------------------------
    # Actions -- Accounts
    # ------------------------------------------------------------------

    @action("Get accounts linked to an access token")
    async def get_accounts(
        self,
        access_token: str,
    ) -> PaginatedList[PlaidAccount]:
        """Retrieve all financial accounts for the given access token.

        Args:
            access_token: A Plaid access token from a completed Link flow.

        Returns:
            Paginated list of PlaidAccount objects.
        """
        data = await self._request(
            "/accounts/get",
            json={"access_token": access_token},
        )

        accounts = [self._parse_account(a) for a in data.get("accounts", [])]

        return PaginatedList(
            items=accounts,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Transactions
    # ------------------------------------------------------------------

    @action("Get transactions for a date range")
    async def get_transactions(
        self,
        access_token: str,
        start_date: str,
        end_date: str,
        limit: int = 100,
        offset: int = 0,
    ) -> PaginatedList[PlaidTransaction]:
        """Retrieve transactions for the specified date range.

        Args:
            access_token: A Plaid access token.
            start_date: Start date in ``YYYY-MM-DD`` format.
            end_date: End date in ``YYYY-MM-DD`` format.
            limit: Maximum number of transactions (max 500).
            offset: Offset for pagination.

        Returns:
            Paginated list of PlaidTransaction objects.
        """
        body: dict[str, Any] = {
            "access_token": access_token,
            "start_date": start_date,
            "end_date": end_date,
            "options": {
                "count": min(limit, 500),
                "offset": offset,
            },
        }
        data = await self._request("/transactions/get", json=body)

        transactions = [self._parse_transaction(t) for t in data.get("transactions", [])]
        total = data.get("total_transactions", 0)
        fetched = offset + len(transactions)

        return PaginatedList(
            items=transactions,
            page_state=PageState(
                offset=fetched,
                has_more=fetched < total,
            ),
            total_count=total,
        )

    # ------------------------------------------------------------------
    # Actions -- Balances
    # ------------------------------------------------------------------

    @action("Get real-time account balances")
    async def get_balance(
        self,
        access_token: str,
    ) -> PaginatedList[PlaidBalance]:
        """Retrieve real-time balance information for all accounts.

        Args:
            access_token: A Plaid access token.

        Returns:
            Paginated list of PlaidBalance objects (one per account).
        """
        data = await self._request(
            "/accounts/balance/get",
            json={"access_token": access_token},
        )

        balances: list[PlaidBalance] = []
        for account in data.get("accounts", []):
            bal_data = account.get("balances", {})
            account_id = account.get("account_id", "")
            balances.append(self._parse_balance(bal_data, account_id))

        return PaginatedList(
            items=balances,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Identity
    # ------------------------------------------------------------------

    @action("Get identity information for accounts")
    async def get_identity(
        self,
        access_token: str,
    ) -> PaginatedList[PlaidAccount]:
        """Retrieve identity information (owner names, addresses, emails).

        The returned accounts include identity data in their response.

        Args:
            access_token: A Plaid access token.

        Returns:
            Paginated list of PlaidAccount objects with identity data.
        """
        data = await self._request(
            "/identity/get",
            json={"access_token": access_token},
        )

        accounts = [self._parse_account(a) for a in data.get("accounts", [])]

        return PaginatedList(
            items=accounts,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Institutions
    # ------------------------------------------------------------------

    @action("Get institution details by ID")
    async def get_institution(
        self,
        institution_id: str,
    ) -> PlaidInstitution:
        """Retrieve details about a specific financial institution.

        Args:
            institution_id: The Plaid institution ID (e.g. ``"ins_109508"``).

        Returns:
            The requested PlaidInstitution.
        """
        data = await self._request(
            "/institutions/get_by_id",
            json={
                "institution_id": institution_id,
                "country_codes": ["US"],
            },
        )

        institution = data.get("institution", {})
        return self._parse_institution(institution)

    @action("Search for institutions by name")
    async def search_institutions(
        self,
        query: str,
        country_codes: Optional[list[str]] = None,
    ) -> PaginatedList[PlaidInstitution]:
        """Search for financial institutions by name.

        Args:
            query: Institution name search query.
            country_codes: Country codes to search within (default ``["US"]``).

        Returns:
            Paginated list of matching PlaidInstitution objects.
        """
        codes = country_codes or ["US"]
        data = await self._request(
            "/institutions/search",
            json={
                "query": query,
                "country_codes": codes,
                "products": ["transactions"],
            },
        )

        institutions = [self._parse_institution(i) for i in data.get("institutions", [])]

        return PaginatedList(
            items=institutions,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Link Token
    # ------------------------------------------------------------------

    @action("Create a Link token for client-side initialization")
    async def create_link_token(
        self,
        user_client_id: str,
        products: list[str],
    ) -> PlaidLinkToken:
        """Create a Link token for initialising Plaid Link on the client.

        Args:
            user_client_id: A unique identifier for the end user.
            products: List of Plaid products to enable
                (e.g. ``["transactions", "auth"]``).

        Returns:
            A PlaidLinkToken containing the token and expiration.
        """
        data = await self._request(
            "/link/token/create",
            json={
                "user": {"client_user_id": user_client_id},
                "client_name": "ToolsConnector",
                "products": products,
                "country_codes": ["US"],
                "language": "en",
            },
        )

        return PlaidLinkToken(
            link_token=data.get("link_token", ""),
            expiration=data.get("expiration", ""),
            request_id=data.get("request_id", ""),
        )

    @action("Exchange a public token for an access token")
    async def exchange_public_token(
        self,
        public_token: str,
    ) -> dict[str, str]:
        """Exchange a public token from Plaid Link for a permanent access token.

        Args:
            public_token: The temporary public token from Plaid Link.

        Returns:
            Dict containing ``access_token`` and ``item_id``.
        """
        data = await self._request(
            "/item/public_token/exchange",
            json={"public_token": public_token},
        )

        return {
            "access_token": data.get("access_token", ""),
            "item_id": data.get("item_id", ""),
            "request_id": data.get("request_id", ""),
        }

    # ------------------------------------------------------------------
    # Actions -- Investments
    # ------------------------------------------------------------------

    @action("Get investment holdings for an access token")
    async def get_investment_holdings(
        self,
        access_token: str,
    ) -> list[PlaidHolding]:
        """Retrieve investment holdings for the linked accounts.

        Args:
            access_token: A Plaid access token with the investments product.

        Returns:
            List of PlaidHolding objects.
        """
        data = await self._request(
            "/investments/holdings/get",
            json={"access_token": access_token},
        )
        return [
            PlaidHolding(
                account_id=h.get("account_id", ""),
                security_id=h.get("security_id"),
                quantity=h.get("quantity", 0.0),
                institution_price=h.get("institution_price"),
                institution_value=h.get("institution_value"),
                cost_basis=h.get("cost_basis"),
                iso_currency_code=h.get("iso_currency_code"),
            )
            for h in data.get("holdings", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Liabilities
    # ------------------------------------------------------------------

    @action("Get liabilities for an access token")
    async def get_liabilities(
        self,
        access_token: str,
    ) -> dict[str, list[PlaidLiability]]:
        """Retrieve liabilities (credit, student, mortgage) for linked accounts.

        Args:
            access_token: A Plaid access token with the liabilities product.

        Returns:
            Dict keyed by liability type with lists of PlaidLiability objects.
        """
        data = await self._request(
            "/liabilities/get",
            json={"access_token": access_token},
        )
        liabilities = data.get("liabilities", {})
        result: dict[str, list[PlaidLiability]] = {}
        for liability_type in ("credit", "student", "mortgage"):
            items = liabilities.get(liability_type, [])
            if items:
                result[liability_type] = [
                    PlaidLiability(
                        account_id=item.get("account_id", ""),
                        type=liability_type,
                        last_payment_amount=item.get("last_payment_amount"),
                        last_payment_date=item.get("last_payment_date"),
                        minimum_payment_amount=item.get("minimum_payment_amount"),
                        next_payment_due_date=item.get("next_payment_due_date"),
                        aprs=item.get("aprs", []),
                    )
                    for item in items
                ]
        return result

    # ------------------------------------------------------------------
    # Actions -- Processor token
    # ------------------------------------------------------------------

    @action("Create a processor token for a third-party integration")
    async def create_processor_token(
        self,
        access_token: str,
        account_id: str,
        processor: str,
    ) -> PlaidProcessorToken:
        """Create a processor token for use with a payment processor.

        Args:
            access_token: A Plaid access token.
            account_id: The account ID to create the processor token for.
            processor: Processor name (e.g. ``"dwolla"``, ``"stripe"``).

        Returns:
            PlaidProcessorToken with the generated token.
        """
        data = await self._request(
            "/processor/token/create",
            json={
                "access_token": access_token,
                "account_id": account_id,
                "processor": processor,
            },
        )
        return PlaidProcessorToken(
            processor_token=data.get("processor_token", ""),
            request_id=data.get("request_id", ""),
        )

    # ------------------------------------------------------------------
    # Actions -- Auth (account & routing numbers)
    # ------------------------------------------------------------------

    @action("Get account and routing numbers")
    async def get_auth(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """Retrieve bank account and routing numbers for ACH payments.

        Requires the ``auth`` product to be enabled for the Item.

        Args:
            access_token: A Plaid access token with the auth product.

        Returns:
            Dict containing ``accounts`` and ``numbers`` (ACH, EFT, etc.).
        """
        data = await self._request(
            "/auth/get",
            json={"access_token": access_token},
        )
        return data

    # ------------------------------------------------------------------
    # Actions -- Item management
    # ------------------------------------------------------------------

    @action("Get Item details")
    async def get_item(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """Retrieve metadata about a linked Item (bank connection).

        Returns information about the Item's status, institution,
        available products, and consent expiration.

        Args:
            access_token: A Plaid access token.

        Returns:
            Dict containing ``item`` and ``status`` objects.
        """
        data = await self._request(
            "/item/get",
            json={"access_token": access_token},
        )
        return data

    @action("Remove a linked Item", dangerous=True)
    async def remove_item(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """Remove a linked Item and invalidate its access token.

        This is a destructive action -- the access token will be
        permanently invalidated and all associated data removed.

        Args:
            access_token: A Plaid access token to remove.

        Returns:
            Dict confirming the removal with request_id.
        """
        data = await self._request(
            "/item/remove",
            json={"access_token": access_token},
        )
        return data

    # ------------------------------------------------------------------
    # Actions -- Item webhook management
    # ------------------------------------------------------------------

    @action("Update the webhook URL for an Item")
    async def item_webhook_update(
        self,
        access_token: str,
        webhook: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update or remove the webhook URL associated with an Item.

        When set, Plaid sends real-time notifications (e.g.
        ``TRANSACTIONS``, ``ITEM`` status changes) to the provided URL.
        Pass ``None`` to remove the webhook.

        Args:
            access_token: A Plaid access token.
            webhook: The new webhook URL, or ``None`` to remove.

        Returns:
            Dict containing the updated ``item`` object.
        """
        body: dict[str, Any] = {"access_token": access_token}
        if webhook is not None:
            body["webhook"] = webhook
        else:
            body["webhook"] = None

        data = await self._request(
            "/item/webhook/update",
            json=body,
        )
        return data

    # ------------------------------------------------------------------
    # Actions -- Investment transactions
    # ------------------------------------------------------------------

    @action("Get investment transactions for a date range")
    async def get_investment_transactions(
        self,
        access_token: str,
        start_date: str,
        end_date: str,
        limit: int = 100,
        offset: int = 0,
    ) -> PaginatedList[PlaidInvestmentTransaction]:
        """Retrieve investment transactions for the specified date range.

        Returns buy, sell, dividend, and other investment transactions
        for up to 24 months of history.

        Args:
            access_token: A Plaid access token with the investments product.
            start_date: Start date in ``YYYY-MM-DD`` format.
            end_date: End date in ``YYYY-MM-DD`` format.
            limit: Maximum number of transactions (max 500).
            offset: Offset for pagination.

        Returns:
            Paginated list of PlaidInvestmentTransaction objects.
        """
        body: dict[str, Any] = {
            "access_token": access_token,
            "start_date": start_date,
            "end_date": end_date,
            "options": {
                "count": min(limit, 500),
                "offset": offset,
            },
        }
        data = await self._request(
            "/investments/transactions/get",
            json=body,
        )

        txns = [
            PlaidInvestmentTransaction(
                investment_transaction_id=t.get(
                    "investment_transaction_id",
                    "",
                ),
                account_id=t.get("account_id", ""),
                security_id=t.get("security_id"),
                date=t.get("date", ""),
                name=t.get("name", ""),
                quantity=t.get("quantity", 0.0),
                amount=t.get("amount", 0.0),
                price=t.get("price", 0.0),
                type=t.get("type", ""),
                subtype=t.get("subtype"),
                iso_currency_code=t.get("iso_currency_code"),
                unofficial_currency_code=t.get("unofficial_currency_code"),
            )
            for t in data.get("investment_transactions", [])
        ]
        total = data.get("total_investment_transactions", 0)
        fetched = offset + len(txns)

        return PaginatedList(
            items=txns,
            page_state=PageState(
                offset=fetched,
                has_more=fetched < total,
            ),
            total_count=total,
        )

    @action("Refresh investment data for an Item")
    async def refresh_investments(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """Trigger a refresh of investment holdings and transactions.

        The refresh is asynchronous -- Plaid will send a webhook when
        the updated data is available.

        Args:
            access_token: A Plaid access token with the investments product.

        Returns:
            Dict confirming the refresh request with ``request_id``.
        """
        data = await self._request(
            "/investments/refresh",
            json={"access_token": access_token},
        )
        return data
