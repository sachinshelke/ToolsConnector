"""SendGrid connector — email sending, contacts, lists, templates, and stats."""

from __future__ import annotations

from .connector import SendGrid
from .types import (
    SendGridContact,
    SendGridJobId,
    SendGridList,
    SendGridResponse,
    SendGridStat,
    SendGridStatMetrics,
    SendGridTemplate,
    SendGridTemplateVersion,
)

__all__ = [
    "SendGrid",
    "SendGridContact",
    "SendGridJobId",
    "SendGridList",
    "SendGridResponse",
    "SendGridStat",
    "SendGridStatMetrics",
    "SendGridTemplate",
    "SendGridTemplateVersion",
]
