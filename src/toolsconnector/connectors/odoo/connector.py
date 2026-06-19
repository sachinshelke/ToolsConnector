"""Odoo connector -- read and write any Odoo model via the JSON-RPC external API.

Odoo (formerly OpenERP) exposes its *entire* ORM over a single JSON-RPC
endpoint. Every business object -- contacts (``res.partner``), sales orders
(``sale.order``), invoices (``account.move``), leads (``crm.lead``), products,
inventory moves, HR records, and anything a custom module adds -- is reached
through the same handful of ORM methods: ``search_read``, ``search_count``,
``read``, ``create``, ``write``, ``unlink``, ``name_search``, ``fields_get``,
``read_group``, plus arbitrary model methods.

This connector exposes those ORM methods as standardized actions, so you get
the **full** power of Odoo -- including its domain filter language and
``read_group`` aggregation -- through one consistent interface, instead of a
curated, lossy subset. ``fields_get`` lets an agent discover a model's schema
at runtime; ``call_method`` is the universal escape hatch for business methods
like ``action_confirm`` or ``action_post``.

Credentials are a JSON string or dict::

    {
        "url": "https://yourcompany.odoo.com",
        "db": "yourcompany",
        "username": "you@example.com",
        "api_key": "<API key from Preferences > Account Security>"
    }

``password`` is accepted as an alias for ``api_key``. Modern Odoo (14+) issues
per-user API keys; with two-factor authentication enabled an API key is
*required* -- a login password will not authenticate over the external API.
This connector is BYOK: it performs only the protocol exchange and never
stores tokens.

Transport: the connector speaks JSON-RPC over ``httpx`` directly (no
``odoorpc``/``erppeek`` wrapper) -- keeping the dependency footprint to the
core ``httpx`` already shipped, and the code async-native.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.errors import (
    APIError,
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    TransportError,
    ValidationError,
)
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    TimeoutError as ToolsConnectorTimeoutError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import OdooVersion

# ----------------------------------------------------------------------------
# Credential parsing
# ----------------------------------------------------------------------------
# Odoo needs a 4-part credential (instance URL, database, login, API key).
# We accept several common aliases for each so callers can paste whatever their
# Odoo admin handed them. Mirrors the structured-credential pattern used by the
# AWS connectors (JSON string or dict -> typed credential).

_URL_KEYS = ("url", "host", "base_url", "instance_url", "server")
_DB_KEYS = ("db", "database", "dbname", "db_name")
_USER_KEYS = ("username", "login", "user", "email")
_KEY_KEYS = ("api_key", "apikey", "api-key", "password", "key", "token")


@dataclass(frozen=True)
class OdooCredentials:
    """Parsed Odoo connection credentials.

    Attributes:
        url: Instance base URL, e.g. ``https://yourcompany.odoo.com`` (no
            trailing slash).
        db: Database name on that instance.
        username: Login (usually an email address).
        api_key: API key (or login password on instances without 2FA).
    """

    url: str
    db: str
    username: str
    api_key: str


def _pick(data: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    """Return the first truthy value among ``keys`` in ``data`` as a string."""
    for k in keys:
        if k in data and data[k]:
            return str(data[k])
    return None


def parse_credentials(raw: Any) -> OdooCredentials:
    """Parse Odoo credentials from a JSON string, dict, or OdooCredentials.

    Args:
        raw: Credentials as a JSON object string, a dict, or an already-parsed
            :class:`OdooCredentials`.

    Returns:
        A validated :class:`OdooCredentials`.

    Raises:
        ValueError: If the payload is malformed or missing a required field.
    """
    if isinstance(raw, OdooCredentials):
        return raw
    if raw is None:
        raise ValueError(
            "Odoo credentials are required. Provide a JSON object with "
            "'url', 'db', 'username', and 'api_key' (or 'password')."
        )
    if isinstance(raw, str):
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(
                "Odoo credentials must be a JSON object with 'url', 'db', "
                "'username', and 'api_key' -- could not parse the string as JSON."
            ) from e
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ValueError(
            f"Odoo credentials must be a JSON string or dict, got {type(raw).__name__}."
        )
    if not isinstance(data, dict):
        raise ValueError("Odoo credentials JSON must be an object (mapping).")

    url = _pick(data, _URL_KEYS)
    db = _pick(data, _DB_KEYS)
    username = _pick(data, _USER_KEYS)
    api_key = _pick(data, _KEY_KEYS)

    missing = [
        label
        for label, val in (
            ("url", url),
            ("db", db),
            ("username", username),
            ("api_key (or password)", api_key),
        )
        if not val
    ]
    if missing:
        raise ValueError(
            "Odoo credentials missing required field(s): "
            f"{', '.join(missing)}. Provide url, db, username, and api_key."
        )
    # mypy: the missing-check above guarantees these are non-None.
    assert url and db and username and api_key
    return OdooCredentials(
        url=url.rstrip("/"),
        db=db,
        username=username,
        api_key=api_key,
    )


def _coerce_int(value: Any, default: Optional[int]) -> Optional[int]:
    """Coerce an int-ish value, mapping ``None`` (MCP synthetic default) to ``default``."""
    if value is None:
        return default
    return int(value)


# Odoo exception class -> typed ToolsConnector error. Keyed on the short class
# name (the suffix after the last dot of ``error.data.name``).
_FAULT_MAP = {
    "AccessDenied": InvalidCredentialsError,
    "AccessError": PermissionDeniedError,
    "MissingError": NotFoundError,
    "ValidationError": ValidationError,
    "UserError": ValidationError,
    "ValueError": ValidationError,
}


class Odoo(BaseConnector):
    """Connect to an Odoo (formerly OpenERP) instance via its JSON-RPC API.

    Exposes Odoo's full ORM -- search, read, create, update, delete, schema
    introspection, and aggregation -- over any model (``res.partner``,
    ``sale.order``, ``account.move``, ``crm.lead``, custom modules, ...).

    Credentials are a JSON string or dict with ``url``, ``db``, ``username``,
    and ``api_key`` (``password`` accepted as an alias). Use an Odoo 14+ API
    key; with 2FA enabled an API key is mandatory.
    """

    name = "odoo"
    display_name = "Odoo"
    category = ConnectorCategory.CRM
    protocol = ProtocolType.JSON_RPC
    # Live-verified 2026-06-19 against a real Odoo 19.3 (saas~19.3) instance:
    # all 11 actions exercised end-to-end (seed + read/write/unlink + read_group
    # via formatted_read_group).
    verification_status = "live"
    # The instance URL is supplied per-connection via credentials, so there is
    # no single class-level base URL.
    base_url = None
    description = (
        "Connect to Odoo (OpenERP) to read and write any model -- contacts, "
        "sales orders, invoices, leads, inventory, HR -- through its ORM: "
        "search_read, create, write, unlink, fields_get, read_group, and "
        "arbitrary business methods, over JSON-RPC."
    )
    # Odoo publishes no fixed external-API rate limit (it is typically your own
    # server). This is a conservative client-side courtesy default; override via
    # the connector config for beefier instances or tighter SaaS plans.
    _rate_limit_config = RateLimitSpec(rate=20, period=1, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and open the httpx client (no network call yet)."""
        creds = parse_credentials(self._credentials)
        self._db = creds.db
        self._login = creds.username
        self._api_key = creds.api_key
        # Explicit base_url override (constructor arg) wins over the credential URL.
        self._instance_url = (self._base_url or creds.url).rstrip("/")

        self._uid: Optional[int] = None
        self._uid_lock = asyncio.Lock()
        self._req_id = 0

        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            base_url=self._instance_url,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        """Return a monotonically increasing JSON-RPC request id."""
        self._req_id += 1
        return self._req_id

    async def _jsonrpc(self, service: str, method: str, args: list[Any]) -> Any:
        """Execute one JSON-RPC ``call`` against the instance.

        Args:
            service: Odoo service name (``"common"`` or ``"object"``).
            method: Service method (``"version"``, ``"authenticate"``,
                ``"execute_kw"``).
            args: Positional argument list for the service method.

        Returns:
            The decoded ``result`` payload.

        Raises:
            toolsconnector.errors.ToolsConnectorError subclass: on transport
                failure, a non-2xx HTTP status, or an Odoo application fault.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": self._next_id(),
        }
        url = f"{self._instance_url}/jsonrpc"
        try:
            response = await self._client.post("/jsonrpc", json=payload)
        except httpx.TimeoutException as e:
            raise ToolsConnectorTimeoutError(
                f"Odoo request timed out after {self._timeout}s",
                connector=self.name,
                details={"url": url, "underlying": type(e).__name__},
            ) from e
        except httpx.ConnectError as e:
            raise ToolsConnectorConnectionError(
                f"Could not connect to Odoo at {self._instance_url}",
                connector=self.name,
                details={"url": url, "underlying": str(e)},
            ) from e
        except httpx.TransportError as e:
            raise TransportError(
                f"Odoo transport error: {type(e).__name__}",
                connector=self.name,
                details={"url": url, "underlying": str(e)},
            ) from e

        # JSON-RPC returns HTTP 200 even for application faults; treat any
        # non-2xx as an infrastructure/proxy error via the shared mapper.
        if response.status_code != 200:
            raise_typed_for_status(response, connector=self.name)

        try:
            body = response.json()
        except ValueError as e:
            raise TransportError(
                f"Odoo returned a non-JSON body (HTTP {response.status_code})",
                connector=self.name,
                details={
                    "url": url,
                    "status_code": response.status_code,
                    "body_preview": (response.text or "")[:200],
                },
            ) from e

        if isinstance(body, dict) and body.get("error"):
            self._raise_odoo_fault(body["error"])

        return body.get("result") if isinstance(body, dict) else None

    def _raise_odoo_fault(self, error: dict[str, Any]) -> None:
        """Translate a JSON-RPC ``error`` object into a typed exception.

        Odoo nests the originating exception class under ``error.data.name``
        (e.g. ``odoo.exceptions.AccessError``) and a human message under
        ``error.data.message``. We map the class to our error taxonomy and fall
        back to :class:`APIError` for anything unrecognised.
        """
        data = error.get("data") or {}
        name = str(data.get("name") or "")
        short = name.rsplit(".", 1)[-1]
        message = (data.get("message") or error.get("message") or "Odoo request failed").strip()
        details = {"odoo_exception": name or None, "debug": data.get("debug")}

        exc_cls = _FAULT_MAP.get(short, APIError)
        suggestion = None
        if exc_cls is InvalidCredentialsError:
            suggestion = (
                "Check url, db, username, and api_key. With 2FA enabled you "
                "must use an API key, not a login password."
            )
        raise exc_cls(
            message,
            connector=self.name,
            suggestion=suggestion,
            details=details,
        )

    async def _ensure_uid(self) -> int:
        """Authenticate once and cache the resulting user id (``uid``).

        Returns:
            The integer ``uid`` Odoo assigns to the authenticated session.

        Raises:
            InvalidCredentialsError: If authentication fails (wrong url/db/
                login/key, or 2FA requiring an API key).
        """
        if self._uid is not None:
            return self._uid
        async with self._uid_lock:
            if self._uid is not None:  # re-check after acquiring the lock
                return self._uid
            result = await self._jsonrpc(
                "common", "authenticate", [self._db, self._login, self._api_key, {}]
            )
            # Odoo returns False (or 0) for bad credentials rather than a fault.
            if not result:
                raise InvalidCredentialsError(
                    "Odoo authentication failed -- check url, db, username, and "
                    "api_key. With 2FA enabled you must use an API key, not a "
                    "login password.",
                    connector=self.name,
                    details={"db": self._db, "username": self._login},
                )
            self._uid = int(result)
            return self._uid

    async def _call(
        self,
        model: str,
        method: str,
        args: Optional[list[Any]] = None,
        kwargs: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Dispatch one ORM method via ``execute_kw`` (authenticated)."""
        uid = await self._ensure_uid()
        return await self._jsonrpc(
            "object",
            "execute_kw",
            [self._db, uid, self._api_key, model, method, list(args or []), dict(kwargs or {})],
        )

    # ------------------------------------------------------------------
    # Actions -- the generic ORM primitive
    # ------------------------------------------------------------------

    @action("Get the Odoo server version (connectivity / capability check)")
    async def get_version(self) -> OdooVersion:
        """Return the Odoo server version info. Requires no authentication, so
        it doubles as a connectivity check.

        Returns:
            An :class:`OdooVersion` with ``server_version``, ``server_serie``,
            and ``protocol_version``.
        """
        result = await self._jsonrpc("common", "version", [])
        return OdooVersion(**(result or {}))

    @action("Search and read records of any Odoo model in one call")
    async def search_read(
        self,
        model: str,
        domain: Optional[list[Any]] = None,
        fields: Optional[list[str]] = None,
        limit: int = 50,
        offset: int = 0,
        order: Optional[str] = None,
    ) -> PaginatedList[dict[str, Any]]:
        """Search a model and return matching records' field values.

        The primary read action. It exposes Odoo's full *domain* filter
        language: a list of ``[field, operator, value]`` triplets combined with
        the prefix logical operators ``'&'`` (and -- the implicit default),
        ``'|'`` (or), and ``'!'`` (not). Relational fields can be traversed with
        dotted paths (e.g. ``"country_id.code"``).

        Args:
            model: Technical model name -- e.g. ``"res.partner"`` (contacts),
                ``"sale.order"`` (sales orders), ``"account.move"`` (invoices),
                ``"crm.lead"`` (leads), ``"product.product"``.
            domain: Odoo search domain, e.g.
                ``[["customer_rank", ">", 0], ["country_id.code", "=", "US"]]``.
                Omit (or pass ``[]``) to match every record.
            fields: Field names to return. Omit to return all readable fields
                (heavier). Use :meth:`fields_get` to discover field names.
            limit: Maximum records per page (default 50).
            offset: Records to skip -- pass the previous page's
                ``page_state.offset`` to fetch the next page.
            order: Sort clause, e.g. ``"create_date desc"`` or ``"name asc"``.

        Returns:
            Paginated list of records; each record is a dict of
            ``field name -> value``.
        """
        search_domain = domain if domain is not None else []
        page_limit = _coerce_int(limit, 50) or 50
        start = _coerce_int(offset, 0) or 0
        call_kwargs: dict[str, Any] = {"limit": page_limit, "offset": start}
        if fields:
            call_kwargs["fields"] = fields
        if order:
            call_kwargs["order"] = order

        records = await self._call(model, "search_read", [search_domain], call_kwargs)
        records = records or []
        return PaginatedList(
            items=records,
            page_state=PageState(
                offset=start + len(records),
                has_more=len(records) == page_limit,
            ),
        )

    @action("Count records of an Odoo model matching a domain filter")
    async def search_count(self, model: str, domain: Optional[list[Any]] = None) -> int:
        """Count records matching a domain -- far cheaper than reading them.

        Args:
            model: Technical model name.
            domain: Odoo search domain; omit to count all records.

        Returns:
            The number of matching records.
        """
        count = await self._call(model, "search_count", [domain if domain is not None else []])
        return int(count or 0)

    @action("Read specific records of an Odoo model by their IDs")
    async def read(
        self, model: str, ids: list[int], fields: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """Read field values for records whose IDs you already have.

        Args:
            model: Technical model name.
            ids: Record IDs to read.
            fields: Field names to return; omit for all readable fields.

        Returns:
            A list of records as ``field name -> value`` dicts.
        """
        call_kwargs: dict[str, Any] = {}
        if fields:
            call_kwargs["fields"] = fields
        records = await self._call(model, "read", [ids], call_kwargs)
        return records or []

    @action("Create a new record of any Odoo model")
    async def create(self, model: str, values: dict[str, Any]) -> int:
        """Create a record and return its new integer ID.

        NOTE: Odoo has no idempotency keys -- retrying a failed create may
        produce a duplicate. Treat this as a non-idempotent write.

        Args:
            model: Technical model name, e.g. ``"res.partner"``.
            values: ``field name -> value`` map for the new record, e.g.
                ``{"name": "ACME Inc", "email": "hello@acme.com"}``.

        Returns:
            The integer ID of the newly created record.
        """
        new_id = await self._call(model, "create", [values])
        return int(new_id)

    @action("Update existing records of an Odoo model")
    async def write(self, model: str, ids: list[int], values: dict[str, Any]) -> bool:
        """Update one or more records in place.

        Args:
            model: Technical model name.
            ids: IDs of the records to update.
            values: ``field name -> new value`` map applied to every listed
                record.

        Returns:
            ``True`` on success.
        """
        ok = await self._call(model, "write", [ids, values])
        return bool(ok)

    @action("Delete records of an Odoo model by their IDs")
    async def unlink(self, model: str, ids: list[int]) -> bool:
        """Permanently delete records.

        WARNING: This is a hard delete. Prefer archiving (``write`` with
        ``{"active": False}``) on models that support it.

        Args:
            model: Technical model name.
            ids: IDs of the records to delete.

        Returns:
            ``True`` on success.
        """
        ok = await self._call(model, "unlink", [ids])
        return bool(ok)

    @action("Find records by display name (typeahead-style lookup)")
    async def name_search(
        self,
        model: str,
        name: str = "",
        limit: int = 50,
        operator: str = "ilike",
    ) -> list[list[Any]]:
        """Resolve a human name to record IDs -- e.g. find the partner ID for
        "ACME" before creating an order.

        Args:
            model: Technical model name.
            name: Text to match against each record's display name.
            limit: Maximum matches to return.
            operator: Match operator (``"ilike"`` = case-insensitive contains,
                the default).

        Returns:
            A list of ``[id, display_name]`` pairs.
        """
        call_kwargs = {
            "name": name or "",
            "operator": operator or "ilike",
            "limit": _coerce_int(limit, 50),
        }
        result = await self._call(model, "name_search", [], call_kwargs)
        return result or []

    @action("Discover the fields (schema) of an Odoo model")
    async def fields_get(
        self, model: str, attributes: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """Introspect a model's fields: names, types, labels, relations, and
        required flags. Call this first when you don't know a model's field
        names -- especially useful for AI agents operating against an unfamiliar
        instance with custom modules.

        Args:
            model: Technical model name, e.g. ``"res.partner"``.
            attributes: Which field attributes to return, e.g.
                ``["string", "type", "required", "relation"]``. Omit for all.

        Returns:
            A dict of ``field name -> {attribute -> value}``.
        """
        call_kwargs: dict[str, Any] = {}
        if attributes:
            call_kwargs["attributes"] = attributes
        result = await self._call(model, "fields_get", [], call_kwargs)
        return result or {}

    @action("Aggregate Odoo records grouped by one or more fields (GROUP BY)")
    async def read_group(
        self,
        model: str,
        domain: Optional[list[Any]] = None,
        fields: Optional[list[str]] = None,
        groupby: Optional[list[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        orderby: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Group-and-aggregate records -- the equivalent of SQL ``GROUP BY``.
        E.g. total invoiced amount per customer, or lead count per stage.

        Works across Odoo versions: modern Odoo (17+/SaaS) removed
        ``read_group`` in favour of ``formatted_read_group``. This action calls
        the modern method and transparently falls back to ``read_group`` on
        legacy instances (<= 16); the choice is cached after the first call.

        Args:
            model: Technical model name.
            domain: Filter applied before grouping; omit for all records.
            fields: Aggregate specs, e.g. ``["amount_total:sum"]`` -- NOT the
                groupby fields. The per-group record ``__count`` is always
                included automatically.
            groupby: Field(s) to group by, e.g. ``["partner_id"]`` or a date
                granularity like ``["create_date:month"]``.
            limit: Maximum groups to return.
            offset: Groups to skip.
            orderby: Sort clause for the groups.

        Returns:
            A list of group dicts, each with the grouped value(s), the
            aggregated measure(s), and a ``__count`` of records in the group.
        """
        search_domain = domain if domain is not None else []
        group_by = groupby or []
        start = _coerce_int(offset, 0) or 0
        resolved_limit = _coerce_int(limit, None)

        # Modern path: formatted_read_group(domain, groupby=, aggregates=, ...).
        # __count is requested explicitly so callers always get a per-group count.
        aggregates = list(fields) if fields else []
        if "__count" not in aggregates:
            aggregates = [*aggregates, "__count"]
        modern_kwargs: dict[str, Any] = {"groupby": group_by, "aggregates": aggregates}
        if start:
            modern_kwargs["offset"] = start
        if resolved_limit:
            modern_kwargs["limit"] = resolved_limit
        if orderby:
            modern_kwargs["order"] = orderby

        if getattr(self, "_frg_supported", None) is not False:
            try:
                result = await self._call(
                    model, "formatted_read_group", [search_domain], modern_kwargs
                )
                self._frg_supported = True
                return result or []
            except APIError as e:
                if "does not exist" not in str(e).lower():
                    raise
                self._frg_supported = False  # legacy Odoo (<= 16)

        # Legacy fallback: the classic read_group(domain, fields, groupby, ...).
        legacy_kwargs: dict[str, Any] = {"lazy": False, "offset": start}
        if resolved_limit:
            legacy_kwargs["limit"] = resolved_limit
        if orderby:
            legacy_kwargs["orderby"] = orderby
        result = await self._call(
            model, "read_group", [search_domain, fields or [], group_by], legacy_kwargs
        )
        return result or []

    @action("Call any method on any Odoo model (advanced escape hatch)")
    async def call_method(
        self,
        model: str,
        method: str,
        args: Optional[list[Any]] = None,
        kwargs: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Invoke an arbitrary ORM or business method via ``execute_kw`` -- the
        universal escape hatch for anything the typed actions above don't cover,
        e.g. ``action_confirm`` on a ``sale.order`` or ``action_post`` on an
        ``account.move``.

        Args:
            model: Technical model name.
            method: Method name to invoke on the model.
            args: Positional argument list (record IDs usually come first), e.g.
                ``[[42]]`` to act on record 42.
            kwargs: Keyword-argument dict for the method.

        Returns:
            Whatever the Odoo method returns (often a bool or an action dict).
        """
        return await self._call(model, method, args or [], kwargs or {})
