"""Microsoft Teams connector -- manage teams, channels, and messages via MS Graph."""

from __future__ import annotations

from .connector import Teams
from .types import (
    Team,
    TeamsChannel,
    TeamsChat,
    TeamsMember,
    TeamsMessage,
    TeamsMessageBody,
    TeamsMessageFrom,
    TeamsPresence,
)

__all__ = [
    "Teams",
    "Team",
    "TeamsChannel",
    "TeamsChat",
    "TeamsMember",
    "TeamsMessage",
    "TeamsMessageBody",
    "TeamsMessageFrom",
    "TeamsPresence",
]
