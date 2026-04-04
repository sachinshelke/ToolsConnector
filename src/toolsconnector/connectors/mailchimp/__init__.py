"""Mailchimp connector -- audience lists, members, and campaigns."""

from __future__ import annotations

from .connector import Mailchimp
from .types import (
    MailchimpCampaign,
    MailchimpCampaignRecipients,
    MailchimpCampaignSettings,
    MailchimpList,
    MailchimpMember,
    MailchimpStats,
)

__all__ = [
    "Mailchimp",
    "MailchimpCampaign",
    "MailchimpCampaignRecipients",
    "MailchimpCampaignSettings",
    "MailchimpList",
    "MailchimpMember",
    "MailchimpStats",
]
