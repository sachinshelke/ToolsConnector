"""XML parsing utilities for AWS API responses.

Generic helpers for extracting data from the XML documents returned by
AWS REST and Query APIs. Works with any XML namespace, unlike the
S3-specific ``find_text`` in ``s3/_helpers.py``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterator, Optional


def find_text(
    element: ET.Element,
    tag: str,
    namespace: Optional[str] = None,
) -> Optional[str]:
    """Find a child element by tag name and return its text content.

    Searches first with the given *namespace*, then falls back to a
    bare (unqualified) tag lookup so callers do not need to know
    whether the response uses a default namespace.

    Args:
        element: Parent XML element to search within.
        tag: Child element tag name (without namespace prefix).
        namespace: Optional XML namespace URI. When provided the
            search uses ``{namespace}tag`` first.

    Returns:
        Text content of the matching child, or ``None`` if not found.
    """
    child: Optional[ET.Element] = None
    if namespace:
        child = element.find(f"{{{namespace}}}{tag}")
    if child is None:
        child = element.find(tag)
    return child.text if child is not None else None


def iter_elements(
    root: ET.Element,
    tag: str,
    namespace: Optional[str] = None,
) -> Iterator[ET.Element]:
    """Yield all descendant elements matching *tag*.

    Searches with the namespace-qualified tag first. If *namespace* is
    ``None`` the bare tag name is used.

    Args:
        root: Root element to search within.
        tag: Element tag name (without namespace prefix).
        namespace: Optional XML namespace URI.

    Yields:
        Matching ``ET.Element`` objects.
    """
    qualified = f"{{{namespace}}}{tag}" if namespace else tag
    yield from root.iter(qualified)

    # When a namespace was given, also yield any bare-tagged elements
    # that the qualified search missed (mixed-namespace responses).
    if namespace:
        seen_qualified = {id(e) for e in root.iter(qualified)}
        for elem in root.iter(tag):
            if id(elem) not in seen_qualified:
                yield elem


def parse_xml_error(xml_text: str) -> dict[str, Optional[str]]:
    """Extract error details from an AWS XML error response.

    AWS XML error responses typically have the structure::

        <ErrorResponse>
          <Error>
            <Code>AccessDenied</Code>
            <Message>Access Denied</Message>
          </Error>
          <RequestId>...</RequestId>
        </ErrorResponse>

    Or for S3::

        <Error>
          <Code>NoSuchBucket</Code>
          <Message>The specified bucket does not exist</Message>
          <RequestId>...</RequestId>
        </Error>

    Args:
        xml_text: Raw XML response body string.

    Returns:
        Dict with ``code``, ``message``, and ``request_id`` keys
        (values may be ``None`` if not present).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"code": None, "message": xml_text, "request_id": None}

    # Try <ErrorResponse><Error>... structure first.
    error_elem = root.find("Error")
    if error_elem is None:
        # Try namespace-qualified variants.
        for ns in (
            "https://iam.amazonaws.com/doc/2010-05-08/",
            "https://ec2.amazonaws.com/doc/2016-11-15/",
        ):
            error_elem = root.find(f"{{{ns}}}Error")
            if error_elem is not None:
                break

    # S3-style: root *is* the <Error> element.
    if error_elem is None and root.tag in ("Error", "ErrorResponse"):
        error_elem = root

    if error_elem is None:
        error_elem = root

    code = find_text(error_elem, "Code") or find_text(root, "Code")
    message = find_text(error_elem, "Message") or find_text(root, "Message")
    request_id = (
        find_text(error_elem, "RequestId")
        or find_text(root, "RequestId")
        or find_text(root, "RequestID")
    )

    return {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
