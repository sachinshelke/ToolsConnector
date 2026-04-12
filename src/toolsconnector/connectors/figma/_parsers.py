"""Figma API response parsers.

Helper functions to parse raw JSON dicts from the Figma REST API
into typed Pydantic models.
"""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    FigmaClientMeta,
    FigmaComment,
    FigmaComponent,
    FigmaComponentSet,
    FigmaFile,
    FigmaImage,
    FigmaPage,
    FigmaProject,
    FigmaProjectFile,
    FigmaStyle,
    FigmaUser,
    FigmaVersion,
)


def _parse_user(data: Optional[dict[str, Any]]) -> Optional[FigmaUser]:
    """Parse a FigmaUser from API JSON.

    Args:
        data: Raw JSON dict or None.

    Returns:
        FigmaUser instance or None.
    """
    if not data:
        return None
    return FigmaUser(
        id=data.get("id"),
        handle=data.get("handle"),
        img_url=data.get("img_url"),
    )


def _parse_client_meta(
    data: Optional[dict[str, Any]],
) -> Optional[FigmaClientMeta]:
    """Parse positional metadata for a comment.

    Args:
        data: Raw client_meta dict or None.

    Returns:
        FigmaClientMeta instance or None.
    """
    if not data:
        return None
    return FigmaClientMeta(
        x=data.get("x"),
        y=data.get("y"),
        node_id=data.get("node_id"),
        node_offset=data.get("node_offset"),
    )


def parse_file(data: dict[str, Any]) -> FigmaFile:
    """Parse a FigmaFile from API JSON.

    Args:
        data: Raw JSON dict from the Figma API.

    Returns:
        A FigmaFile instance.
    """
    return FigmaFile(
        name=data.get("name"),
        last_modified=data.get("lastModified"),
        thumbnail_url=data.get("thumbnailUrl"),
        version=data.get("version"),
        role=data.get("role"),
        editor_type=data.get("editorType"),
        schema_version=data.get("schemaVersion"),
    )


def parse_version(data: dict[str, Any]) -> FigmaVersion:
    """Parse a FigmaVersion from API JSON.

    Args:
        data: Raw JSON dict for a file version.

    Returns:
        A FigmaVersion instance.
    """
    return FigmaVersion(
        id=data["id"],
        created_at=data.get("created_at"),
        label=data.get("label"),
        description=data.get("description"),
        user=_parse_user(data.get("user")),
    )


def parse_comment(data: dict[str, Any]) -> FigmaComment:
    """Parse a FigmaComment from API JSON.

    Args:
        data: Raw JSON dict for a comment.

    Returns:
        A FigmaComment instance.
    """
    return FigmaComment(
        id=data["id"],
        message=data.get("message"),
        file_key=data.get("file_key"),
        parent_id=data.get("parent_id"),
        user=_parse_user(data.get("user")),
        created_at=data.get("created_at"),
        resolved_at=data.get("resolved_at"),
        order_id=data.get("order_id"),
        client_meta=_parse_client_meta(data.get("client_meta")),
    )


def parse_project(data: dict[str, Any]) -> FigmaProject:
    """Parse a FigmaProject from API JSON.

    Args:
        data: Raw JSON dict for a project.

    Returns:
        A FigmaProject instance.
    """
    return FigmaProject(
        id=data["id"],
        name=data.get("name"),
    )


def parse_project_file(data: dict[str, Any]) -> FigmaProjectFile:
    """Parse a FigmaProjectFile from API JSON.

    Args:
        data: Raw JSON dict for a project file entry.

    Returns:
        A FigmaProjectFile instance.
    """
    return FigmaProjectFile(
        key=data["key"],
        name=data.get("name"),
        thumbnail_url=data.get("thumbnail_url"),
        last_modified=data.get("last_modified"),
    )


def parse_component(data: dict[str, Any]) -> FigmaComponent:
    """Parse a FigmaComponent from API JSON.

    Args:
        data: Raw JSON dict for a component.

    Returns:
        A FigmaComponent instance.
    """
    return FigmaComponent(
        key=data["key"],
        name=data.get("name"),
        description=data.get("description"),
        file_key=data.get("file_key"),
        node_id=data.get("node_id"),
        thumbnail_url=data.get("thumbnail_url"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        user=_parse_user(data.get("user")),
    )


def parse_style(data: dict[str, Any]) -> FigmaStyle:
    """Parse a FigmaStyle from API JSON.

    Args:
        data: Raw JSON dict for a style.

    Returns:
        A FigmaStyle instance.
    """
    return FigmaStyle(
        key=data["key"],
        name=data.get("name"),
        description=data.get("description"),
        style_type=data.get("style_type"),
        file_key=data.get("file_key"),
        node_id=data.get("node_id"),
        thumbnail_url=data.get("thumbnail_url"),
        sort_position=data.get("sort_position"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        user=_parse_user(data.get("user")),
    )


def parse_page(data: dict[str, Any]) -> FigmaPage:
    """Parse a FigmaPage from a Figma document canvas node.

    Args:
        data: Raw JSON dict for a document child (canvas/page).

    Returns:
        A FigmaPage instance.
    """
    return FigmaPage(
        id=data["id"],
        name=data.get("name"),
        type=data.get("type", "CANVAS"),
    )


def parse_component_set(data: dict[str, Any]) -> FigmaComponentSet:
    """Parse a FigmaComponentSet from API JSON.

    Args:
        data: Raw JSON dict for a component set.

    Returns:
        A FigmaComponentSet instance.
    """
    return FigmaComponentSet(
        key=data["key"],
        name=data.get("name"),
        description=data.get("description"),
        file_key=data.get("file_key"),
        node_id=data.get("node_id"),
        thumbnail_url=data.get("thumbnail_url"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        user=_parse_user(data.get("user")),
    )


def parse_image(node_id: str, url: Optional[str], err: Optional[str] = None) -> FigmaImage:
    """Build a FigmaImage from the images response mapping.

    Args:
        node_id: The node ID the image corresponds to.
        url: URL of the rendered image.
        err: Error message if rendering failed.

    Returns:
        A FigmaImage instance.
    """
    return FigmaImage(
        node_id=node_id,
        image_url=url,
        error=err,
    )
