"""Slack connector — send messages, manage channels, and interact with workspaces."""

from __future__ import annotations

from .connector import Slack
from .types import Channel, Message, SlackFile, SlackUser

__all__ = [
    "Slack",
    "Channel",
    "Message",
    "SlackFile",
    "SlackUser",
]
