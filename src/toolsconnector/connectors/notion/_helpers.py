"""Response parsers for the Notion connector."""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    NotionBlock,
    NotionComment,
    NotionDatabase,
    NotionPage,
    NotionProperty,
    NotionRichText,
    NotionUser,
)


def parse_user(data: Optional[dict[str, Any]]) -> Optional[NotionUser]:
    """Parse a raw Notion user dict into a NotionUser, or None if absent.

    Notion's API returns nested user objects on many shapes (created_by,
    last_edited_by, people property values, comment authors). The shape
    is the same everywhere — extract once, reuse everywhere.

    Notion users come in two flavors: ``person`` (a workspace member) or
    ``bot`` (an integration). Both carry id + optional name + optional
    avatar_url; the ``type`` field disambiguates. We default to ``person``
    when the type is missing — bots can only be returned by the
    /v1/users/me endpoint, where the caller's own action sets type="bot".
    """
    if not data:
        return None
    return NotionUser(
        id=data["id"],
        name=data.get("name"),
        avatar_url=data.get("avatar_url"),
        type=data.get("type", "person"),
    )


def parse_page(data: dict[str, Any]) -> NotionPage:
    """Parse a raw Notion page JSON into a NotionPage model.

    Property values that don't conform to the NotionProperty schema are
    skipped rather than aborting the whole page parse. Two cases trigger
    this defensive path:

    1. **Non-dict values** (None, str, list at the top) — corrupted or
       unexpected response shape.
    2. **Dict values that fail NotionProperty validation** — happens when
       a non-page object (e.g., a database returned by /search) is fed
       to parse_page. Database properties carry *schema configuration*
       (e.g., ``rich_text: {}``) where page properties carry *values*
       (``rich_text: [<rich_text_segment>, …]``); the latter is what
       NotionProperty models.

    Dropping the offending property is preferable to crashing — the page
    object itself, including all its other (well-formed) properties,
    remains usable.
    """
    from pydantic import ValidationError as _PydanticValidationError

    props: dict[str, NotionProperty] = {}
    for key, val in data.get("properties", {}).items():
        if not isinstance(val, dict):
            continue
        try:
            props[key] = NotionProperty(**val)
        except _PydanticValidationError:
            # Shape doesn't match the property-value schema. Skip and
            # carry on rather than crashing the entire page parse.
            continue

    return NotionPage(
        id=data["id"],
        object=data.get("object", "page"),
        created_time=data.get("created_time"),
        last_edited_time=data.get("last_edited_time"),
        created_by=parse_user(data.get("created_by")),
        last_edited_by=parse_user(data.get("last_edited_by")),
        archived=data.get("archived", False),
        url=data.get("url"),
        parent=data.get("parent", {}),
        properties=props,
        icon=data.get("icon"),
        cover=data.get("cover"),
    )


def parse_block(data: dict[str, Any]) -> NotionBlock:
    """Parse a raw Notion block JSON into a NotionBlock model."""
    block_type = data.get("type", "")
    return NotionBlock(
        id=data["id"],
        object=data.get("object", "block"),
        type=block_type,
        created_time=data.get("created_time"),
        last_edited_time=data.get("last_edited_time"),
        created_by=parse_user(data.get("created_by")),
        last_edited_by=parse_user(data.get("last_edited_by")),
        archived=data.get("archived", False),
        has_children=data.get("has_children", False),
        parent=data.get("parent", {}),
        content=data.get(block_type, {}),
    )


def parse_comment(data: dict[str, Any]) -> NotionComment:
    """Parse a raw Notion comment JSON into a NotionComment model."""
    rich_text = [NotionRichText(**rt) for rt in data.get("rich_text", [])]
    return NotionComment(
        id=data["id"],
        object=data.get("object", "comment"),
        parent=data.get("parent", {}),
        discussion_id=data.get("discussion_id"),
        created_time=data.get("created_time"),
        last_edited_time=data.get("last_edited_time"),
        created_by=parse_user(data.get("created_by")),
        rich_text=rich_text,
    )


def parse_database(data: dict[str, Any]) -> NotionDatabase:
    """Parse a raw Notion database JSON into a NotionDatabase model."""
    title_items = [NotionRichText(**t) for t in data.get("title", [])]
    desc_items = [NotionRichText(**d) for d in data.get("description", [])]
    return NotionDatabase(
        id=data["id"],
        object=data.get("object", "database"),
        title=title_items,
        description=desc_items,
        created_time=data.get("created_time"),
        last_edited_time=data.get("last_edited_time"),
        created_by=parse_user(data.get("created_by")),
        last_edited_by=parse_user(data.get("last_edited_by")),
        archived=data.get("archived", False),
        url=data.get("url"),
        parent=data.get("parent", {}),
        properties=data.get("properties", {}),
        icon=data.get("icon"),
        cover=data.get("cover"),
        is_inline=data.get("is_inline", False),
    )
