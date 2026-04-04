"""Microsoft Teams connector -- manage teams, channels, and messages via MS Graph."""

from __future__ import annotations

from .connector import Teams
from .types import Team, TeamsChannel, TeamsMember, TeamsMessage

__all__ = [
    "Teams",
    "Team",
    "TeamsChannel",
    "TeamsMessage",
    "TeamsMember",
]
