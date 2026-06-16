"""Declarative HTTP binding for the Notion connector.

This is the *load-bearing* source of truth for how every bindable Notion action
maps to an ``httpx.Request`` (method, path, query/body placement, value
envelopes, pagination). ``connector.py`` builds its requests from this via
``toolsconnector.spec.executor.build_request`` — there is no second, imperative
copy of the wire shape.

Coverage: 21 of 24 actions are fully declarative. The 3 escape hatches stay
imperative because their request *shape branches on argument values* — not
something a finite, serializable binding should encode:

- ``search``       — ``filter_type`` becomes a two-field object
  ``{"value": ..., "property": "object"}`` AND results are post-filtered to
  ``object == "page"``.
- ``create_page``  — the ``parent`` envelope flips between ``{"page_id": ...}``
  and ``{"database_id": ...}`` and a title property is conditionally injected,
  depending on whether ``properties`` was supplied.
- ``add_comment``  — body is either ``{"parent": {"page_id": ...}, ...}`` or a
  top-level ``{"discussion_id": ..., ...}`` depending on ``discussion_id``.

Notion idioms the binding *does* capture declaratively (via the IR's named
value-wraps) instead of pushing to escape hatches:

- ``wrap="rich_text"``  — a scalar string becomes ``[{"text": {"content": x}}]``
  (update_comment, update_database title/description, create_database title).
- ``wrap="object"``     — a scalar becomes ``{wrap_key: x}``
  (create_database ``parent`` -> ``{"page_id": parent_id}``).
- constant body field   — ``archived`` defaulted to ``True``/``False`` with no
  caller arg (archive_page / restore_page).
- ``raw_body_param``    — the whole JSON body IS the caller's dict
  (update_block ``content``).

Pagination: Notion's cursor scheme is ``OFFSET_TOKEN`` — the response
``next_cursor`` is fed back as the ``cursor`` arg (``start_cursor`` on the wire),
in the POST body for write endpoints and the query string for read endpoints.
"""

from __future__ import annotations

from toolsconnector.spec.binding import (
    ActionBinding,
    AuthKind,
    ConnectorBinding,
    EndpointBinding,
    Location,
    PaginationBinding,
    PaginationKind,
    ParamBinding,
)

_NOTION_VERSION = "2022-06-28"

# ---------------------------------------------------------------------------
# Param helpers
# ---------------------------------------------------------------------------


def _path(name: str, wire: str | None = None) -> ParamBinding:
    """A required path-template parameter (percent-encoded by the executor)."""
    return ParamBinding(name=name, wire=wire or name, location=Location.PATH, required=True)


def _page_size(location: Location, default: int) -> ParamBinding:
    """The ``limit`` -> ``page_size`` param, clamped to Notion's [1, 100] range.

    Mirrors the connector's ``_clamp_limit(limit, default=...)``: the per-action
    default kicks in when the caller omits the arg (or MCP passes ``None``); the
    value is clamped to ``max(1, min(limit, 100))`` by the executor.
    """
    return ParamBinding(
        name="limit",
        wire="page_size",
        location=location,
        default=default,
        min=1,
        max=100,
        ty="number",
    )


def _cursor(location: Location) -> ParamBinding:
    """The ``cursor`` -> ``start_cursor`` pagination param."""
    return ParamBinding(name="cursor", wire="start_cursor", location=location)


def _body(
    name: str, *, wire: str | None = None, required: bool = False, ty: str = "object"
) -> ParamBinding:
    return ParamBinding(
        name=name, wire=wire or name, location=Location.BODY, required=required, ty=ty
    )


# Notion's cursor pagination: response.next_cursor -> next call's `cursor` arg,
# guarded by has_more. Same kind whether the cursor rides in the body (POST
# endpoints) or the query string (GET endpoints).
def _offset(token_in_body: bool) -> PaginationBinding:  # noqa: ARG001 - kind is location-agnostic
    return PaginationBinding(
        kind=PaginationKind.OFFSET_TOKEN,
        items_field="results",
        token_field="next_cursor",
        token_param_py="cursor",
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

_ACTIONS = [
    # -- Pages --------------------------------------------------------------
    ActionBinding(
        name="get_page",
        method="GET",
        endpoint="main",
        path="/pages/{page_id}",
        params=[_path("page_id")],
    ),
    ActionBinding(
        name="update_page",
        method="PATCH",
        endpoint="main",
        path="/pages/{page_id}",
        params=[_path("page_id"), _body("properties", required=True)],
    ),
    # archive/restore: same path, constant body field via default (no caller arg).
    ActionBinding(
        name="archive_page",
        method="PATCH",
        endpoint="main",
        path="/pages/{page_id}",
        params=[
            _path("page_id"),
            ParamBinding(
                name="archived", wire="archived", location=Location.BODY, default=True, ty="boolean"
            ),
        ],
    ),
    ActionBinding(
        name="restore_page",
        method="PATCH",
        endpoint="main",
        path="/pages/{page_id}",
        params=[
            _path("page_id"),
            ParamBinding(
                name="archived",
                wire="archived",
                location=Location.BODY,
                default=False,
                ty="boolean",
            ),
        ],
    ),
    ActionBinding(
        name="get_page_property",
        method="GET",
        endpoint="main",
        path="/pages/{page_id}/properties/{property_id}",
        params=[
            _path("page_id"),
            _path("property_id"),
            _page_size(Location.QUERY, 100),
            _cursor(Location.QUERY),
        ],
        pagination=_offset(token_in_body=False),
    ),
    # -- Databases ----------------------------------------------------------
    ActionBinding(
        name="get_database",
        method="GET",
        endpoint="main",
        path="/databases/{database_id}",
        params=[_path("database_id")],
    ),
    ActionBinding(
        name="query_database",
        method="POST",
        endpoint="main",
        path="/databases/{database_id}/query",
        params=[
            _path("database_id"),
            _page_size(Location.BODY, 50),
            _body("filter"),
            _body("sorts", ty="object[]"),
            _cursor(Location.BODY),
        ],
        pagination=_offset(token_in_body=True),
    ),
    ActionBinding(
        name="create_database",
        method="POST",
        endpoint="main",
        path="/databases",
        params=[
            ParamBinding(
                name="parent_id",
                wire="parent",
                location=Location.BODY,
                wrap="object",
                wrap_key="page_id",
                required=True,
                ty="string",
            ),
            ParamBinding(
                name="title",
                wire="title",
                location=Location.BODY,
                wrap="rich_text",
                required=True,
                ty="string",
            ),
            _body("properties", required=True),
        ],
    ),
    ActionBinding(
        name="update_database",
        method="PATCH",
        endpoint="main",
        path="/databases/{database_id}",
        params=[
            _path("database_id"),
            ParamBinding(
                name="title", wire="title", location=Location.BODY, wrap="rich_text", ty="string"
            ),
            ParamBinding(
                name="description",
                wire="description",
                location=Location.BODY,
                wrap="rich_text",
                ty="string",
            ),
            _body("properties"),
        ],
    ),
    # -- Blocks -------------------------------------------------------------
    ActionBinding(
        name="get_block",
        method="GET",
        endpoint="main",
        path="/blocks/{block_id}",
        params=[_path("block_id")],
    ),
    ActionBinding(
        name="get_block_children",
        method="GET",
        endpoint="main",
        path="/blocks/{block_id}/children",
        params=[_path("block_id"), _page_size(Location.QUERY, 50), _cursor(Location.QUERY)],
        pagination=_offset(token_in_body=False),
    ),
    ActionBinding(
        name="append_block_children",
        method="PATCH",
        endpoint="main",
        path="/blocks/{block_id}/children",
        params=[_path("block_id"), _body("children", required=True, ty="object[]")],
    ),
    # content dict is passed through verbatim as the entire body.
    ActionBinding(
        name="update_block",
        method="PATCH",
        endpoint="main",
        path="/blocks/{block_id}",
        params=[_path("block_id")],
        raw_body_param="content",
    ),
    ActionBinding(
        name="delete_block",
        method="DELETE",
        endpoint="main",
        path="/blocks/{block_id}",
        params=[_path("block_id")],
    ),
    # -- Users --------------------------------------------------------------
    ActionBinding(name="list_users", method="GET", endpoint="main", path="/users"),
    ActionBinding(
        name="get_user",
        method="GET",
        endpoint="main",
        path="/users/{user_id}",
        params=[_path("user_id")],
    ),
    ActionBinding(name="get_me", method="GET", endpoint="main", path="/users/me"),
    # -- Comments -----------------------------------------------------------
    # block_id rides in the QUERY string here (not the path).
    ActionBinding(
        name="list_comments",
        method="GET",
        endpoint="main",
        path="/comments",
        params=[
            ParamBinding(name="block_id", wire="block_id", location=Location.QUERY, required=True),
            _page_size(Location.QUERY, 50),
            _cursor(Location.QUERY),
        ],
        pagination=_offset(token_in_body=False),
    ),
    ActionBinding(
        name="get_comment",
        method="GET",
        endpoint="main",
        path="/comments/{comment_id}",
        params=[_path("comment_id")],
    ),
    ActionBinding(
        name="update_comment",
        method="PATCH",
        endpoint="main",
        path="/comments/{comment_id}",
        params=[
            _path("comment_id"),
            ParamBinding(
                name="text",
                wire="rich_text",
                location=Location.BODY,
                wrap="rich_text",
                required=True,
                ty="string",
            ),
        ],
    ),
    ActionBinding(
        name="delete_comment",
        method="DELETE",
        endpoint="main",
        path="/comments/{comment_id}",
        params=[_path("comment_id")],
    ),
]


NOTION = ConnectorBinding(
    name="notion",
    default_endpoint="main",
    endpoints={
        "main": EndpointBinding(
            id="main",
            base_url="https://api.notion.com/v1",
            encoding="json",
            auth_kind=AuthKind.BEARER,
            auth_header="Authorization",
            extra_headers={"Notion-Version": _NOTION_VERSION},
        )
    },
    actions={a.name: a for a in _ACTIONS},
    # Request shape branches on argument *values* — honest escape hatches.
    escape_hatches=["search", "create_page", "add_comment"],
)

NOTION_BINDING = NOTION

__all__ = ["NOTION", "NOTION_BINDING"]
