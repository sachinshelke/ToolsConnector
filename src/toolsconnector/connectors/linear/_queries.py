"""GraphQL query fragments and templates for the Linear connector."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Field selection fragments
# ---------------------------------------------------------------------------

USER_FIELDS = """
    id
    name
    displayName
    email
    avatarUrl
    active
"""

STATE_FIELDS = """
    id
    name
    type
    color
    position
"""

LABEL_FIELDS = """
    id
    name
    color
"""

ISSUE_FIELDS = f"""
    id
    identifier
    title
    description
    priority
    priorityLabel
    url
    createdAt
    updatedAt
    completedAt
    canceledAt
    dueDate
    estimate
    state {{
        {STATE_FIELDS}
    }}
    assignee {{
        {USER_FIELDS}
    }}
    creator {{
        {USER_FIELDS}
    }}
    team {{
        id
    }}
    project {{
        id
    }}
    labels {{
        nodes {{
            {LABEL_FIELDS}
        }}
    }}
"""

TEAM_FIELDS = """
    id
    name
    key
    description
    icon
    color
    visibility
"""
# `Team.private` was deprecated by Linear (see schema deprecation reason
# "Use `Team.visibility` instead"). We request `visibility` (enum:
# "public" | "private" | "secret") and derive the old boolean in the
# parser so `LinearTeam.private` keeps working for existing callers.

PROJECT_FIELDS = f"""
    id
    name
    description
    slugId
    status {{
        id
        name
        type
        color
    }}
    url
    createdAt
    updatedAt
    startedAt
    targetDate
    progress
    lead {{
        {USER_FIELDS}
    }}
"""
# `Project.state` was deprecated by Linear (see schema deprecation
# reason "Use project.status instead"). The replacement is a nested
# `ProjectStatus` object with `type` carrying the same string the old
# `state` field used to return ("started", "completed", "paused",
# etc.). The parser maps `status.type` → `LinearProject.state` for
# backwards compat; the richer status object is also surfaced via the
# extra fields stored on the model (extra="ignore" tolerates them).

COMMENT_FIELDS = f"""
    id
    body
    createdAt
    updatedAt
    url
    user {{
        {USER_FIELDS}
    }}
    issue {{
        id
    }}
"""

CYCLE_FIELDS = """
    id
    number
    name
    description
    startsAt
    endsAt
    completedAt
    progress
    team {
        id
    }
"""
