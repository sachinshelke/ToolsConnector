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
    private
"""

PROJECT_FIELDS = f"""
    id
    name
    description
    slugId
    state
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
