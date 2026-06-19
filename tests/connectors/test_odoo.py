"""End-to-end tests for the Odoo connector using respx.

Odoo is our first JSON-RPC connector — a *single* endpoint (``POST /jsonrpc``)
where the model, method, and credentials all travel in the request body, not in
the URL or headers. The tests mirror the per-connector playbook
(test_linear.py / test_notion.py) but adapt to the RPC-specific surface:

  - **Single endpoint, body-dispatched**: every call hits ``POST /jsonrpc``.
    We assert on the body's ``params.service`` / ``params.method`` / ``args``,
    not on URL paths. A shared handler routes ``common.version`` /
    ``common.authenticate`` / ``object.execute_kw`` by body.
  - **Two requests per action**: an authenticated action first does
    ``authenticate`` (handshake → uid), then ``execute_kw``. We pin that the
    uid is cached so a *second* action does NOT re-authenticate.
  - **Credentials in the body, not a header**: the api_key is the 3rd
    positional arg of ``execute_kw`` / ``authenticate``; there is no
    Authorization header. We assert both.
  - **Args are the boundary**: domain triplets and values travel as JSON args,
    never interpolated into a string — adversarial input cannot change the
    request shape.
  - **Fault mapping**: a JSON-RPC ``error`` body (HTTP 200) with
    ``data.name == "odoo.exceptions.AccessError"`` → PermissionDeniedError,
    ``AccessDenied`` → InvalidCredentialsError, ``MissingError`` → NotFoundError,
    ``ValidationError`` / ``UserError`` → ValidationError.
  - **Offset pagination**: ``limit`` / ``offset`` in, ``page_state.offset`` +
    ``has_more`` out, over a 2-page sequence.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.odoo import Odoo
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from toolsconnector.spec.connector import ProtocolType

BASE = "https://demo.odoo.test"
DB = "demo"
LOGIN = "admin"
KEY = "fake_api_key_0123456789"
UID = 7

_VERSION = {
    "server_version": "17.0",
    "server_version_info": [17, 0, 0, "final", 0, ""],
    "server_serie": "17.0",
    "protocol_version": 1,
}


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def odoo() -> Odoo:
    """Odoo connector pointed at a fake instance.

    Credentials never leave the process — respx intercepts at the httpx
    transport layer. Tests `await` the `a`-prefixed async methods
    (`asearch_read`, `acreate`, ...) that BaseConnector installs per @action.
    """
    connector = Odoo(credentials={"url": BASE, "db": DB, "username": LOGIN, "api_key": KEY})
    await connector._setup()
    yield connector
    await connector._teardown()


def _body(call: respx.models.Call) -> dict[str, Any]:
    """Decode a captured JSON-RPC request body."""
    return json.loads(call.request.read())


def _params(call: respx.models.Call) -> dict[str, Any]:
    """Decode the ``params`` of a captured JSON-RPC request."""
    return _body(call)["params"]


def make_handler(
    *,
    uid: int = UID,
    authenticate: Optional[Any] = None,
    execute_result: Any = None,
    execute_error: Optional[dict[str, Any]] = None,
    version: Optional[dict[str, Any]] = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Build a respx side-effect that dispatches one /jsonrpc route by body.

    ``execute_result`` may be a static value or a callable ``(args) -> result``
    that inspects the execute_kw positional args (``[db, uid, pw, model,
    method, pos_args, kwargs]``) to vary the response per call (e.g. paging).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        rid = body.get("id")
        p = body["params"]
        service, method, args = p["service"], p["method"], p["args"]

        def ok(result: Any) -> httpx.Response:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid, "result": result})

        if service == "common" and method == "version":
            return ok(version if version is not None else _VERSION)
        if service == "common" and method == "authenticate":
            return ok(authenticate if authenticate is not None else uid)
        if service == "object" and method == "execute_kw":
            if execute_error is not None:
                return httpx.Response(
                    200, json={"jsonrpc": "2.0", "id": rid, "error": execute_error}
                )
            result = execute_result(args) if callable(execute_result) else execute_result
            return ok(result)
        return ok(None)

    return handler


# ---------------------------------------------------------------------------
# 1. Happy path — search_read wire shape + auth handshake ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_read_wire_shape_and_handshake(odoo: Odoo) -> None:
    """search_read: authenticate first, then execute_kw with the exact envelope."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post("/jsonrpc").mock(
            side_effect=make_handler(
                execute_result=[{"id": 1, "name": "ACME"}, {"id": 2, "name": "Globex"}]
            )
        )

        result = await odoo.asearch_read(
            "res.partner",
            domain=[["customer_rank", ">", 0]],
            fields=["name", "email"],
            limit=2,
        )

        assert [r["name"] for r in result.items] == ["ACME", "Globex"]

        # Two requests: handshake then the ORM call.
        assert len(route.calls) == 2
        auth = _params(route.calls[0])
        assert auth["service"] == "common" and auth["method"] == "authenticate"
        assert auth["args"][:3] == [DB, LOGIN, KEY]  # db, login, api_key

        call = _params(route.calls[1])
        assert call["service"] == "object" and call["method"] == "execute_kw"
        db, uid, key, model, orm_method, pos_args, kwargs = call["args"]
        assert (db, uid, key) == (DB, UID, KEY)  # uid threaded from handshake
        assert model == "res.partner" and orm_method == "search_read"
        assert pos_args == [[["customer_rank", ">", 0]]]  # domain wrapped in args[0]
        assert kwargs == {"limit": 2, "offset": 0, "fields": ["name", "email"]}

        # JSON-RPC envelope is well-formed.
        env = _body(route.calls[1])
        assert env["jsonrpc"] == "2.0" and env["method"] == "call"

        # Credentials travel in the body — NOT in an Authorization header.
        assert "authorization" not in {k.lower() for k in route.calls[1].request.headers}


# ---------------------------------------------------------------------------
# 2. uid caching — a second action does NOT re-authenticate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uid_is_cached_across_actions(odoo: Odoo) -> None:
    """authenticate runs once; subsequent actions reuse the cached uid."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/jsonrpc").mock(side_effect=make_handler(execute_result=1))

        await odoo.asearch_count("res.partner")
        await odoo.asearch_count("sale.order")

        methods = [_params(c)["method"] for c in route.calls]
        assert methods.count("authenticate") == 1  # handshake only once
        assert methods.count("execute_kw") == 2  # both counts ran


# ---------------------------------------------------------------------------
# 3. get_version needs no authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_version_skips_auth(odoo: Odoo) -> None:
    """get_version hits common.version directly — no handshake, typed result."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/jsonrpc").mock(side_effect=make_handler())

        version = await odoo.aget_version()

        assert version.server_version == "17.0"
        assert version.protocol_version == 1
        assert len(route.calls) == 1
        assert _params(route.calls[0])["method"] == "version"


# ---------------------------------------------------------------------------
# 4. create — returns the new int id, values travel verbatim in args[0]
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_returns_id_and_passes_values(odoo: Odoo) -> None:
    """create: execute_kw('create', [values]) -> new id; values untouched."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/jsonrpc").mock(side_effect=make_handler(execute_result=42))

        values = {"name": "O'Brien & Co", "email": "a@b.c"}
        new_id = await odoo.acreate("res.partner", values)

        assert new_id == 42
        call = _params(route.calls[-1])
        _, _, _, model, orm_method, pos_args, _ = call["args"]
        assert model == "res.partner" and orm_method == "create"
        # The value dict (incl. the apostrophe) is carried as JSON, not
        # interpolated — no escaping bugs, no injection surface.
        assert pos_args == [values]


# ---------------------------------------------------------------------------
# 5. Offset pagination — limit/offset in, page_state.offset + has_more out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_read_offset_pagination(odoo: Odoo) -> None:
    """Page 1 fills the limit (has_more True); page 2 is short (has_more False)."""

    def pager(args: list[Any]) -> Any:
        _, _, _, _, method, _, kwargs = args
        if method == "search_read":
            offset = kwargs.get("offset", 0)
            return [{"id": 1}, {"id": 2}] if offset == 0 else [{"id": 3}]
        return None

    with respx.mock(base_url=BASE) as mock:
        mock.post("/jsonrpc").mock(side_effect=make_handler(execute_result=pager))

        page1 = await odoo.asearch_read("res.partner", limit=2, offset=0)
        assert [r["id"] for r in page1.items] == [1, 2]
        assert page1.page_state.offset == 2
        assert page1.page_state.has_more is True

        page2 = await odoo.asearch_read("res.partner", limit=2, offset=page1.page_state.offset)
        assert [r["id"] for r in page2.items] == [3]
        assert page2.page_state.offset == 3
        assert page2.page_state.has_more is False


# ---------------------------------------------------------------------------
# 6. Fault mapping — JSON-RPC error body (HTTP 200) -> typed exceptions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("odoo_exc", "expected"),
    [
        ("odoo.exceptions.AccessError", PermissionDeniedError),
        ("odoo.exceptions.AccessDenied", InvalidCredentialsError),
        ("odoo.exceptions.MissingError", NotFoundError),
        ("odoo.exceptions.ValidationError", ValidationError),
        ("odoo.exceptions.UserError", ValidationError),
    ],
)
@pytest.mark.asyncio
async def test_fault_mapping(odoo: Odoo, odoo_exc: str, expected: type) -> None:
    """error.data.name maps to the right typed ToolsConnector error."""
    error = {
        "code": 200,
        "message": "Odoo Server Error",
        "data": {"name": odoo_exc, "message": "boom", "debug": "traceback..."},
    }
    with respx.mock(base_url=BASE) as mock:
        mock.post("/jsonrpc").mock(side_effect=make_handler(execute_error=error))

        with pytest.raises(expected) as exc_info:
            await odoo.asearch_read("res.partner")
        assert exc_info.value.connector == "odoo"


@pytest.mark.asyncio
async def test_bad_credentials_authenticate_false(odoo: Odoo) -> None:
    """Odoo returns False (not a fault) for bad creds -> InvalidCredentialsError."""
    with respx.mock(base_url=BASE) as mock:
        mock.post("/jsonrpc").mock(side_effect=make_handler(authenticate=False))

        with pytest.raises(InvalidCredentialsError):
            await odoo.asearch_count("res.partner")


# ---------------------------------------------------------------------------
# 7. call_method escape hatch + read_group aggregation wire shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_method_escape_hatch(odoo: Odoo) -> None:
    """call_method forwards model/method/args/kwargs verbatim to execute_kw."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/jsonrpc").mock(side_effect=make_handler(execute_result=True))

        ok = await odoo.acall_method("sale.order", "action_confirm", args=[[5]])
        assert ok is True
        _, _, _, model, orm_method, pos_args, _ = _params(route.calls[-1])["args"]
        assert (model, orm_method, pos_args) == ("sale.order", "action_confirm", [[5]])


@pytest.mark.asyncio
async def test_read_group_modern_wire_shape(odoo: Odoo) -> None:
    """read_group calls formatted_read_group (modern Odoo 17+/SaaS): domain
    positional, groupby + aggregates (with __count auto-added) as kwargs."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/jsonrpc").mock(
            side_effect=make_handler(
                execute_result=[{"partner_id": [1, "ACME"], "amount_total:sum": 99.0, "__count": 3}]
            )
        )

        groups = await odoo.aread_group(
            "sale.order",
            domain=[["state", "=", "sale"]],
            fields=["amount_total:sum"],
            groupby=["partner_id"],
        )
        assert groups[0]["__count"] == 3
        _, _, _, model, orm_method, pos_args, kwargs = _params(route.calls[-1])["args"]
        assert model == "sale.order" and orm_method == "formatted_read_group"
        assert pos_args == [[["state", "=", "sale"]]]  # domain only, positional
        assert kwargs["groupby"] == ["partner_id"]
        assert kwargs["aggregates"] == ["amount_total:sum", "__count"]  # __count auto-added


@pytest.mark.asyncio
async def test_read_group_legacy_fallback(odoo: Odoo) -> None:
    """On legacy Odoo (<=16) formatted_read_group is missing -> the action
    transparently falls back to read_group([domain, fields, groupby], lazy=False)."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        rid = body.get("id")
        p = body["params"]
        if p["service"] == "common" and p["method"] == "authenticate":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid, "result": UID})
        method = p["args"][4]  # execute_kw ORM method
        if method == "formatted_read_group":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {
                        "code": 200,
                        "message": "Server error",
                        "data": {
                            "name": "builtins.AttributeError",
                            "message": "The method 'sale.order.formatted_read_group' does not exist",
                        },
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": rid,
                "result": [{"partner_id": [1, "ACME"], "__count": 2}],
            },
        )

    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/jsonrpc").mock(side_effect=handler)

        groups = await odoo.aread_group(
            "sale.order", fields=["amount_total:sum"], groupby=["partner_id"]
        )
        assert groups[0]["__count"] == 2
        orm_methods = [
            _params(c)["args"][4] for c in route.calls if _params(c)["method"] == "execute_kw"
        ]
        assert orm_methods == ["formatted_read_group", "read_group"]  # tried modern, fell back
        legacy = _params(route.calls[-1])["args"]
        assert legacy[5] == [[], ["amount_total:sum"], ["partner_id"]]  # [domain, fields, groupby]
        assert legacy[6]["lazy"] is False


# ---------------------------------------------------------------------------
# 8. Spec metadata
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    """Protocol, tier, and the full 11-action surface are declared."""
    assert Odoo.protocol is ProtocolType.JSON_RPC
    assert Odoo.verification_status == "live"  # live-verified against Odoo 19.3
    action_names = set(Odoo.get_actions().keys())
    assert action_names == {
        "get_version",
        "search_read",
        "search_count",
        "read",
        "create",
        "write",
        "unlink",
        "name_search",
        "fields_get",
        "read_group",
        "call_method",
    }
