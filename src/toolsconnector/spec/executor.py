"""Generic spec-driven executor — the language-agnostic core (here in Python).

Given a ``ConnectorBinding`` + an action name + a dict of arguments,
``build_request()`` produces the *exact* ``httpx.Request`` the hand-written
connector would send. ``next_request()`` computes the follow-up request for
pagination.

This ~200-line interpreter is the ONLY per-language code a Smithy-style generator
would hand-write (once per language's thin runtime lib). Everything else — the
1,402 typed action methods — is generated from the declarative spec. The point of
the spike: prove this finite interpreter reproduces the imperative connectors.
"""

from __future__ import annotations

import base64
import json as _json
import re
from typing import Any, Optional
from urllib.parse import quote as _url_quote
from urllib.parse import urlencode

import httpx

from .binding import (
    ActionBinding,
    AuthKind,
    ConnectorBinding,
    EndpointBinding,
    Location,
    PaginationKind,
    ParamBinding,
    Style,
)

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="?(\w+)"?')
_PAGE_INFO_RE = re.compile(r"[?&]page_info=([^&>]+)")


# ----------------------------------------------------------------------------
# Context derivation (credential -> template vars)
# ----------------------------------------------------------------------------


def derive_ctx(conn: ConnectorBinding, credential: str) -> dict[str, str]:
    ctx: dict[str, str] = {}
    for cv in conn.ctx_vars:
        if cv.source == "whole":
            ctx[cv.name] = credential
        elif cv.source.startswith("split:"):
            _, idx, sep = cv.source.split(":", 2)
            parts = credential.split(sep)
            i = int(idx)
            ctx[cv.name] = parts[i] if len(parts) > i else ""
    return ctx


def _auth_cred(ep: EndpointBinding, credential: str, ctx: dict[str, str]) -> str:
    if ep.auth_cred_ctx:
        return ctx.get(ep.auth_cred_ctx, "")
    return credential


def _apply_auth(headers: dict[str, str], ep: EndpointBinding, cred: str) -> None:
    if ep.auth_kind == AuthKind.BEARER:
        headers[ep.auth_header] = f"Bearer {cred}"
    elif ep.auth_kind == AuthKind.HEADER_KEY:
        headers[ep.auth_header] = cred
    elif ep.auth_kind == AuthKind.BASIC_SPLIT:
        token = base64.b64encode(cred.encode()).decode()
        headers[ep.auth_header] = f"Basic {token}"
    elif ep.auth_kind == AuthKind.BASIC_USER:
        # API key as username, empty password: base64("<key>:")
        token = base64.b64encode(f"{cred}:".encode()).decode()
        headers[ep.auth_header] = f"Basic {token}"


# ----------------------------------------------------------------------------
# Serialization
# ----------------------------------------------------------------------------


def _present(v: Any) -> bool:
    return v is not None


def _clamp(v: Any, mx: Optional[int]) -> Any:
    if mx is not None and isinstance(v, int):
        return min(v, mx)
    return v


def _styled_pairs(p: ParamBinding, v: Any) -> list[tuple[str, str]]:
    """Serialize ONE present param value into wire (key, value) pairs by style.

    Shared by both query strings and form-encoded bodies — Stripe puts
    list/object params (``payment_method_types[i]``, ``line_items[i][price]``)
    in the BODY, not just the query, so the same finite style vocabulary has to
    drive both. (Pure JSON-body shaping stays in ``_build_body``'s JSON branch.)
    """
    if p.style == Style.INDEXED:
        seq = v[: p.max_items] if p.max_items else v
        return [(f"{p.wire}[{i}]", str(item)) for i, item in enumerate(seq)]
    if p.style == Style.INDEXED_OBJECT:
        out: list[tuple[str, str]] = []
        for i, item in enumerate(v):
            for sk in p.subkeys:
                val = item.get(sk, p.subkey_defaults.get(sk))
                out.append((f"{p.wire}[{i}][{sk}]", str(val)))
        return out
    if p.style == Style.BRACKET:
        seq = v[: p.max_items] if p.max_items else v
        return [(f"{p.wire}[]", str(item)) for item in seq]
    if p.style == Style.FORM_EXPLODE:
        return [(p.wire, str(item)) for item in v]
    if p.style == Style.MAP:
        return [(f"{p.wire}[{k}]", str(val)) for k, val in v.items()]
    # SIMPLE (default)
    return [(p.wire, str(_clamp(v, p.max)))]


def _query_pairs(action: ActionBinding, args: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for p in action.params:
        if p.location != Location.QUERY:
            continue
        v = args.get(p.name, p.default)
        if _present(v):
            out.extend(_styled_pairs(p, v))
    return out


def _build_body(
    action: ActionBinding, encoding: str, args: dict[str, Any]
) -> tuple[Optional[bytes], Optional[str]]:
    body_params = [p for p in action.params if p.location == Location.BODY]
    if not body_params:
        return None, None

    if encoding == "form":
        pairs: list[tuple[str, str]] = []
        for p in body_params:
            v = args.get(p.name, p.default)
            if _present(v):
                pairs.extend(_styled_pairs(p, v))
        return urlencode(pairs).encode(), "application/x-www-form-urlencoded"

    # JSON
    obj: dict[str, Any] = {}
    for p in body_params:
        v = args.get(p.name, p.default)
        if not _present(v):
            continue
        if p.item_wrap:
            seq = v[: p.max_items] if p.max_items else v
            v = [{p.item_wrap: elem} for elem in seq]
        obj[p.body_key or p.wire] = v
    if action.body_wrap:
        obj = {action.body_wrap: obj}
    return _json.dumps(obj, separators=(",", ":")).encode(), "application/json"


# ----------------------------------------------------------------------------
# Request building
# ----------------------------------------------------------------------------


def build_request(
    conn: ConnectorBinding, action_name: str, args: dict[str, Any], credential: str
) -> httpx.Request:
    action = conn.actions[action_name]
    ep = conn.endpoints[action.endpoint]
    ctx = derive_ctx(conn, credential)

    # 1) path: pick the conditional variant (first present-arg wins), then
    #    substitute {ctx} + {path params}
    # Path params are percent-encoded (safe="") to prevent hostile IDs (e.g.
    # "../charges/ch_x") from escaping the intended path prefix via httpx URL
    # normalization — matches the _p() helper in the imperative connectors.
    # Context vars (subst from ctx) are NOT encoded; they are derived from the
    # credential and controlled by the developer, not end-user input.
    subst: dict[str, Any] = dict(ctx)
    for p in action.params:
        if p.location == Location.PATH:
            raw = args.get(p.name, p.default)
            subst[p.wire] = _url_quote(str(raw), safe="") if raw is not None else raw
    chosen_path = action.path
    for pv in action.path_variants:
        if args.get(pv.when_present):  # truthy, matching the connector's `if org:`
            chosen_path = pv.path
            break
    base = ep.base_url.format(**ctx)
    path = chosen_path.format(**subst)
    url_str = base.rstrip("/") + "/" + path.lstrip("/")

    # 2) query
    query = _query_pairs(action, args)
    url = httpx.URL(url_str, params=query) if query else httpx.URL(url_str)

    # 3) body
    encoding = action.body_encoding or ep.encoding
    content, content_type = _build_body(action, encoding, args)

    # 4) headers
    headers: dict[str, str] = dict(ep.extra_headers)
    for p in action.params:
        if p.location == Location.HEADER:
            v = args.get(p.name, p.default)
            if _present(v):
                headers[p.wire] = str(v)
    _apply_auth(headers, ep, _auth_cred(ep, credential, ctx))
    if content_type:
        headers["content-type"] = content_type

    return httpx.Request(action.method, url, content=content, headers=headers)


# ----------------------------------------------------------------------------
# Pagination — compute the next-page request
# ----------------------------------------------------------------------------


def _parse_link_next(link_header: Optional[str], rel: str) -> Optional[str]:
    if not link_header:
        return None
    for url, r in _LINK_RE.findall(link_header):
        if r == rel:
            m = _PAGE_INFO_RE.search(url)
            if m:
                return m.group(1)
    return None


def _parse_link_rel(link_header: Optional[str], rel: str) -> Optional[str]:
    """Return the FULL url for a Link rel (GitHub follows it directly)."""
    if not link_header:
        return None
    for url, r in _LINK_RE.findall(link_header):
        if r == rel:
            return url
    return None


def next_request(
    conn: ConnectorBinding,
    action_name: str,
    prev_args: dict[str, Any],
    credential: str,
    *,
    body: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
) -> Optional[httpx.Request]:
    action = conn.actions[action_name]
    ep = conn.endpoints[action.endpoint]
    ctx = derive_ctx(conn, credential)
    pg = action.pagination
    body = body or {}
    headers = headers or {}

    if pg.kind == PaginationKind.FOLLOW_URL:
        uri = body.get(pg.token_field) if pg.token_field else None
        if not uri:
            return None
        url = httpx.URL(ep.base_url.format(**ctx)).join(uri)
        h: dict[str, str] = dict(ep.extra_headers)
        _apply_auth(h, ep, _auth_cred(ep, credential, ctx))
        return httpx.Request("GET", url, headers=h)

    if pg.kind == PaginationKind.OFFSET_TOKEN:
        cursor = body.get(pg.token_field) if pg.token_field else None
        if cursor is None:
            return None
        nargs = (
            dict(prev_args)
            if pg.carry is None
            else {k: prev_args[k] for k in pg.carry if k in prev_args}
        )
        nargs[pg.token_param_py] = cursor
        return build_request(conn, action_name, nargs, credential)

    if pg.kind == PaginationKind.LAST_ID:
        # Stripe: next cursor is the id of the last item, sent as starting_after,
        # but only while has_more is truthy.
        items = body.get(pg.items_field, []) if pg.items_field else []
        if not (body.get(pg.has_more_field, False) and items):
            return None
        cursor = items[-1].get(pg.id_field)
        if cursor is None:
            return None
        nargs = (
            dict(prev_args)
            if pg.carry is None
            else {k: prev_args[k] for k in pg.carry if k in prev_args}
        )
        nargs[pg.token_param_py] = cursor
        return build_request(conn, action_name, nargs, credential)

    if pg.kind == PaginationKind.LINK_HEADER:
        cursor = _parse_link_next(headers.get("link"), pg.link_rel)
        if not cursor:
            return None
        nargs = (
            dict(prev_args)
            if pg.carry is None
            else {k: prev_args[k] for k in pg.carry if k in prev_args}
        )
        nargs[pg.token_param_py] = cursor
        return build_request(conn, action_name, nargs, credential)

    if pg.kind == PaginationKind.LINK_FOLLOW:
        # GitHub: the Link rel=next URL is absolute and already carries every
        # query param; GET it directly with the connector's standard headers.
        next_url = _parse_link_rel(headers.get("link"), pg.link_rel)
        if not next_url:
            return None
        h = dict(ep.extra_headers)
        _apply_auth(h, ep, _auth_cred(ep, credential, ctx))
        return httpx.Request("GET", next_url, headers=h)

    return None
