"""Shared test fixtures for ToolsConnector."""

from __future__ import annotations

import pytest


@pytest.fixture
def project_root():
    """Return the project root path."""
    from pathlib import Path
    return Path(__file__).parent.parent
