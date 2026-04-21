"""Response parsers for the Notion connector."""

from __future__ import annotations

from typing import Any

from .types import (
    NotionBlock,
    NotionComment,
    NotionDatabase,
    NotionPage,
    NotionProperty,
    NotionRichText,
    NotionUser,
)


def parse_page(data: dict[str, Any]) -> NotionPage:
    """Parse a raw Notion page JSON into a NotionPage model."""
    props: dict[str, NotionProperty] = {}
    for key, val in data.get("properties", {}).items():
        props[key] = NotionProperty(**val)

    return NotionPage(
        id=data["id"],
        object=data.get("object", "page"),
        created_time=data.get("created_time"),
        last_edited_time=data.get("last_edited_time"),
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
        archived=data.get("archived", False),
        has_children=data.get("has_children", False),
        parent=data.get("parent", {}),
        content=data.get(block_type, {}),
    )


def parse_comment(data: dict[str, Any]) -> NotionComment:
    """Parse a raw Notion comment JSON into a NotionComment model."""
    rich_text = [NotionRichText(**rt) for rt in data.get("rich_text", [])]
    created_by_data = data.get("created_by")
    created_by = (
        NotionUser(
            id=created_by_data["id"],
            name=created_by_data.get("name"),
            avatar_url=created_by_data.get("avatar_url"),
            type=created_by_data.get("type", "person"),
        )
        if created_by_data
        else None
    )
    return NotionComment(
        id=data["id"],
        object=data.get("object", "comment"),
        parent=data.get("parent", {}),
        discussion_id=data.get("discussion_id"),
        created_time=data.get("created_time"),
        last_edited_time=data.get("last_edited_time"),
        created_by=created_by,
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
        archived=data.get("archived", False),
        url=data.get("url"),
        parent=data.get("parent", {}),
        properties=data.get("properties", {}),
        icon=data.get("icon"),
        cover=data.get("cover"),
        is_inline=data.get("is_inline", False),
    )
