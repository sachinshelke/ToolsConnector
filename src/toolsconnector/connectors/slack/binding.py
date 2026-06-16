"""Declarative HTTP binding for the Slack connector.

Load-bearing source of truth for how every bindable Slack action maps to an
``httpx.Request``. ``connector.py`` builds its requests from this via
``toolsconnector.spec.executor.build_request``.

Slack specifics the binding encodes:

- **Method = path.** Each Web API method name *is* the path segment under
  ``https://slack.com/api`` (``chat.postMessage`` -> ``/chat.postMessage``).
  There are no path parameters.
- **Reads = GET + query; writes = POST + JSON body.** The connector's client
  defaults to ``Content-Type: application/json``; write payloads are JSON.
- **Query booleans serialize to lowercase** ``"true"``/``"false"``
  (``exclude_archived``, ``include_users``, ``include_disabled``); JSON-body
  booleans stay native (``unfurl_links``, ``is_private``).
- **Per-action ``limit`` clamps** — Slack accepts ``min(limit, 1000)`` for most
  lists, ``min(limit, 100)`` for scheduled messages / search ``count``.
- **Hardcoded literal fields** carried as defaulted params with no caller arg:
  ``conversations.list`` ``types``, ``reactions.get`` ``full=true``,
  ``bookmarks.add`` ``type=link``.
- **py_name != wire_name** renames are explicit per action (e.g.
  ``channel_id``->``channel``, ``emoji``->``name``, ``file_id``->``file``,
  ``user_id``->``user``, ``thread_ts``->``ts``, ``usergroup_id``->``usergroup``).
- **Cursor pagination** (``OFFSET_TOKEN``): the next cursor lives at the dotted
  path ``response_metadata.next_cursor`` and is fed back as ``cursor`` — in the
  query for GET reads, in the body for ``chat.scheduledMessages.list`` (POST).

Escape hatch (1/51): ``upload_file`` (``files.upload``) sends a form-encoded
``data=`` body, not JSON — kept imperative.
"""

from __future__ import annotations

from typing import Any

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

# ---------------------------------------------------------------------------
# Param helpers
# ---------------------------------------------------------------------------


def _q(
    name: str,
    wire: str | None = None,
    *,
    default: Any = None,
    required: bool = False,
    ty: str = "string",
) -> ParamBinding:
    """A query-string parameter."""
    return ParamBinding(
        name=name,
        wire=wire or name,
        location=Location.QUERY,
        default=default,
        required=required,
        ty=ty,
    )


def _b(
    name: str,
    wire: str | None = None,
    *,
    default: Any = None,
    required: bool = False,
    ty: str = "string",
) -> ParamBinding:
    """A JSON-body parameter."""
    return ParamBinding(
        name=name,
        wire=wire or name,
        location=Location.BODY,
        default=default,
        required=required,
        ty=ty,
    )


def _limit_q(default: int, mx: int) -> ParamBinding:
    """``limit`` query param, clamped to ``min(limit, mx)`` like the connector."""
    return ParamBinding(
        name="limit", wire="limit", location=Location.QUERY, default=default, max=mx, ty="number"
    )


def _cursor(location: Location) -> ParamBinding:
    return ParamBinding(name="cursor", wire="cursor", location=location)


def _page(items_field: str) -> PaginationBinding:
    """Slack cursor pagination: response_metadata.next_cursor -> `cursor` arg."""
    return PaginationBinding(
        kind=PaginationKind.OFFSET_TOKEN,
        items_field=items_field,
        token_field="response_metadata.next_cursor",
        token_param_py="cursor",
    )


def _get(
    name: str, endpoint: str, *params: ParamBinding, pagination: PaginationBinding | None = None
) -> ActionBinding:
    return ActionBinding(
        name=name,
        method="GET",
        endpoint="main",
        path=endpoint,
        params=list(params),
        pagination=pagination or PaginationBinding(),
    )


def _postf(
    name: str,
    endpoint: str,
    *params: ParamBinding,
    body_wrap: str | None = None,
    pagination: PaginationBinding | None = None,
) -> ActionBinding:
    return ActionBinding(
        name=name,
        method="POST",
        endpoint="main",
        path=endpoint,
        params=list(params),
        body_wrap=body_wrap,
        pagination=pagination or PaginationBinding(),
    )


# ---------------------------------------------------------------------------
# Actions (50 declarative; upload_file is the escape hatch)
# ---------------------------------------------------------------------------

_ACTIONS = [
    # -- Messaging --------------------------------------------------------------
    _postf(
        "send_message",
        "chat.postMessage",
        _b("channel", required=True),
        _b("text", required=True),
        _b("unfurl_links", default=True, ty="boolean"),
        _b("unfurl_media", default=True, ty="boolean"),
        _b("thread_ts"),
    ),
    _postf(
        "update_message",
        "chat.update",
        _b("channel", required=True),
        _b("ts", required=True),
        _b("text", required=True),
    ),
    _postf("delete_message", "chat.delete", _b("channel", required=True), _b("ts", required=True)),
    _postf(
        "schedule_message",
        "chat.scheduleMessage",
        _b("channel", required=True),
        _b("text", required=True),
        _b("post_at", required=True, ty="number"),
        _b("thread_ts"),
    ),
    _postf(
        "list_scheduled_messages",
        "chat.scheduledMessages.list",
        ParamBinding(
            name="limit", wire="limit", location=Location.BODY, default=100, max=100, ty="number"
        ),
        _b("channel"),
        _cursor(Location.BODY),
        pagination=_page("scheduled_messages"),
    ),
    _postf(
        "delete_scheduled_message",
        "chat.deleteScheduledMessage",
        _b("channel", required=True),
        _b("scheduled_message_id", required=True),
    ),
    _get(
        "get_permalink",
        "chat.getPermalink",
        _q("channel", required=True),
        _q("message_ts", required=True),
    ),
    # -- Channels ---------------------------------------------------------------
    _get(
        "list_channels",
        "conversations.list",
        _q("types", default="public_channel,private_channel"),
        _limit_q(100, 1000),
        _q("exclude_archived", default=False, ty="boolean"),
        _cursor(Location.QUERY),
        pagination=_page("channels"),
    ),
    _get("get_channel", "conversations.info", _q("channel_id", "channel", required=True)),
    _postf(
        "create_channel",
        "conversations.create",
        _b("name", required=True),
        _b("is_private", default=False, ty="boolean"),
    ),
    _postf("archive_channel", "conversations.archive", _b("channel", required=True)),
    _postf("unarchive_channel", "conversations.unarchive", _b("channel", required=True)),
    _postf(
        "rename_channel",
        "conversations.rename",
        _b("channel", required=True),
        _b("name", required=True),
    ),
    _postf(
        "set_channel_topic",
        "conversations.setTopic",
        _b("channel", required=True),
        _b("topic", required=True),
    ),
    _postf(
        "set_channel_purpose",
        "conversations.setPurpose",
        _b("channel", required=True),
        _b("purpose", required=True),
    ),
    _postf(
        "invite_to_channel",
        "conversations.invite",
        _b("channel", required=True),
        _b("users", required=True),
    ),
    _postf(
        "kick_from_channel",
        "conversations.kick",
        _b("channel", required=True),
        _b("user", required=True),
    ),
    _postf("join_channel", "conversations.join", _b("channel", required=True)),
    _postf("leave_channel", "conversations.leave", _b("channel", required=True)),
    _get(
        "list_channel_members",
        "conversations.members",
        _q("channel", required=True),
        _limit_q(100, 1000),
        _cursor(Location.QUERY),
        pagination=_page("members"),
    ),
    _get(
        "list_messages",
        "conversations.history",
        _q("channel", required=True),
        _limit_q(100, 1000),
        _cursor(Location.QUERY),
        _q("oldest"),
        _q("latest"),
        pagination=_page("messages"),
    ),
    _get(
        "list_thread_replies",
        "conversations.replies",
        _q("channel", required=True),
        _q("thread_ts", "ts", required=True),
        _limit_q(100, 1000),
        _cursor(Location.QUERY),
        pagination=_page("messages"),
    ),
    # -- Reactions / pins -------------------------------------------------------
    _postf(
        "add_reaction",
        "reactions.add",
        _b("channel", required=True),
        _b("timestamp", required=True),
        _b("emoji", "name", required=True),
    ),
    _postf(
        "remove_reaction",
        "reactions.remove",
        _b("channel", required=True),
        _b("timestamp", required=True),
        _b("emoji", "name", required=True),
    ),
    _get(
        "get_reactions",
        "reactions.get",
        _q("channel", required=True),
        _q("timestamp", required=True),
        _q("full", default="true"),
    ),
    _postf("pin_message", "pins.add", _b("channel", required=True), _b("timestamp", required=True)),
    _postf(
        "unpin_message", "pins.remove", _b("channel", required=True), _b("timestamp", required=True)
    ),
    _get("list_pins", "pins.list", _q("channel", required=True)),
    # -- Files (upload_file is the escape hatch) --------------------------------
    _postf("delete_file", "files.delete", _b("file_id", "file", required=True)),
    _get("get_file_info", "files.info", _q("file_id", "file", required=True)),
    # -- Users ------------------------------------------------------------------
    _get(
        "list_users",
        "users.list",
        _limit_q(100, 1000),
        _cursor(Location.QUERY),
        pagination=_page("members"),
    ),
    _get("get_user", "users.info", _q("user_id", "user", required=True)),
    _get("lookup_user_by_email", "users.lookupByEmail", _q("email", required=True)),
    _get("get_user_presence", "users.getPresence", _q("user_id", "user", required=True)),
    _get("get_user_profile", "users.profile.get", _q("user_id", "user", required=True)),
    _postf("set_presence", "users.setPresence", _b("presence", required=True)),
    _get(
        "search_messages",
        "search.messages",
        _q("query", required=True),
        _q("sort", default="timestamp"),
        _q("sort_dir", default="desc"),
        ParamBinding(
            name="count", wire="count", location=Location.QUERY, default=20, max=100, ty="number"
        ),
        _q("page", default=1, ty="number"),
    ),
    # status: nested {"profile": {...}} via body_wrap
    _postf(
        "set_status",
        "users.profile.set",
        _b("status_text", required=True),
        _b("status_emoji"),
        _b("expiration", "status_expiration", ty="number"),
        body_wrap="profile",
    ),
    # -- Bookmarks --------------------------------------------------------------
    _postf(
        "add_bookmark",
        "bookmarks.add",
        _b("channel_id", required=True),
        _b("title", required=True),
        _b("type", default="link"),
        _b("link", required=True),
        _b("emoji"),
    ),
    _get("list_bookmarks", "bookmarks.list", _q("channel_id", required=True)),
    _postf(
        "remove_bookmark",
        "bookmarks.remove",
        _b("bookmark_id", required=True),
        _b("channel_id", required=True),
    ),
    # -- Reminders --------------------------------------------------------------
    _postf(
        "add_reminder",
        "reminders.add",
        _b("text", required=True),
        _b("time", required=True),
        _b("user"),
    ),
    _get("list_reminders", "reminders.list"),
    _postf("delete_reminder", "reminders.delete", _b("reminder_id", "reminder", required=True)),
    # -- Misc -------------------------------------------------------------------
    _get("list_emoji", "emoji.list"),
    _postf("auth_test", "auth.test"),
    _get("get_team_info", "team.info"),
    # -- User groups ------------------------------------------------------------
    _postf(
        "create_usergroup",
        "usergroups.create",
        _b("name", required=True),
        _b("handle", required=True),
        _b("description"),
        _b("channels"),
    ),
    _get(
        "list_usergroups",
        "usergroups.list",
        _q("include_users", default=False, ty="boolean"),
        _q("include_disabled", default=False, ty="boolean"),
    ),
    _postf(
        "update_usergroup",
        "usergroups.update",
        _b("usergroup_id", "usergroup", required=True),
        _b("name"),
        _b("handle"),
        _b("description"),
        _b("channels"),
    ),
]


SLACK = ConnectorBinding(
    name="slack",
    default_endpoint="main",
    endpoints={
        "main": EndpointBinding(
            id="main",
            base_url="https://slack.com/api",
            encoding="json",
            auth_kind=AuthKind.BEARER,
            auth_header="Authorization",
        )
    },
    actions={a.name: a for a in _ACTIONS},
    # files.upload uses a form-encoded (data=) body, not JSON — kept imperative.
    escape_hatches=["upload_file"],
)

SLACK_BINDING = SLACK

__all__ = ["SLACK", "SLACK_BINDING"]
