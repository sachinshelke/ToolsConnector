# Project Management

Connectors for issue tracking and project management platforms. 4 connectors, 121 actions.

---

### Jira

**Category:** Project Management | **Auth:** API Token (Basic Auth) | **Actions:** 8

Connect to Jira to search, create, and manage issues, transitions, and projects.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| search_issues | Search issues using JQL | No |
| get_issue | Get details of a specific issue | No |
| create_issue | Create a new issue | Yes |
| update_issue | Update fields on an existing issue | No |
| add_comment | Add a comment to an issue | Yes |
| transition_issue | Move an issue to a different status | Yes |
| list_projects | List all accessible projects | No |
| get_transitions | Get available transitions for an issue | No |

**Quick start:**

```python
kit = ToolKit(["jira"], credentials={"jira": {"email": "you@company.com", "token": "your-api-token", "domain": "yourcompany.atlassian.net"}})
result = kit.execute("jira_search_issues", {"jql": "project = PROJ AND status = 'In Progress'"})
```

---

### Asana

**Category:** Project Management | **Auth:** Personal Access Token | **Actions:** 8

Connect to Asana to manage tasks, projects, and workspaces.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_tasks | List tasks in a project or workspace | No |
| get_task | Get details of a specific task | No |
| create_task | Create a new task | Yes |
| update_task | Update an existing task | No |
| list_projects | List projects in a workspace | No |
| get_project | Get details of a specific project | No |
| add_comment | Add a comment to a task | Yes |
| list_workspaces | List workspaces for the user | No |

**Quick start:**

```python
kit = ToolKit(["asana"], credentials={"asana": "your-personal-access-token"})
result = kit.execute("asana_list_tasks", {"project": "1234567890"})
```

---

### Linear

**Category:** Project Management | **Auth:** API Key (raw, no `Bearer`) | **Actions:** 19 | **Status:** ✅ Tier 1 (16/19 live-verified)

Connect to Linear via the GraphQL API at `api.linear.app/graphql`. The personal API key is sent **raw** in the `Authorization` header — Linear does NOT use the `Bearer` prefix for `lin_api_*` keys. The connector handles this automatically.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_issues | List issues with optional team/state/assignee filters and pagination | No |
| get_issue | Get details of a specific issue by UUID | No |
| create_issue | Create a new issue | Yes |
| update_issue | Update an existing issue | No |
| delete_issue | Permanently delete an issue | Yes |
| search_issues | Search issues by full-text query (uses `searchIssues(term:)`) | No |
| list_teams | List all teams in the workspace | No |
| list_projects | List projects with pagination | No |
| update_project | Update a project's metadata | Yes |
| delete_project | Permanently delete a project | Yes |
| list_users | List workspace members with pagination | No |
| get_user | Get details for a single user | No |
| list_labels | List issue labels, optionally filtered by team | No |
| create_label | Create a new issue label | Yes |
| get_workflow_states | List workflow states for a team | No |
| list_cycles | List cycles (sprints), optionally filtered by team | No |
| get_cycle | Get details for a single cycle | No |
| add_comment | Add a comment to an issue | Yes |
| list_issue_comments | List all comments on an issue | No |

**Quick start:**

```python
kit = ToolKit(["linear"], credentials={"linear": "lin_api_your-api-key"})
result = kit.execute("linear_list_issues", {"team_id": "TEAM-ID", "state": "In Progress"})
```

**Deprecation handling (transparent to callers):** Linear's GraphQL schema deprecates and replaces fields/operations over time. The connector tracks current best practice; existing `LinearTeam.private`, `LinearProject.state`, and `Linear.search_issues(query=...)` call shapes stay populated/working via parser-level backwards-compat mapping. See the connector README's *Deprecation Handling* table for the four migrations applied as of 2026-05-23.

---

### Trello

**Category:** Project Management | **Auth:** API Key + Token | **Actions:** 8

Connect to Trello to manage boards, lists, and cards.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_boards | List boards for the authenticated user | No |
| get_board | Get details of a specific board | No |
| list_lists | List lists on a board | No |
| list_cards | List cards in a list | No |
| get_card | Get details of a specific card | No |
| create_card | Create a new card | Yes |
| update_card | Update an existing card | Yes |
| add_comment | Add a comment to a card | Yes |

**Quick start:**

```python
kit = ToolKit(["trello"], credentials={"trello": {"api_key": "your-key", "token": "your-token"}})
result = kit.execute("trello_list_boards", {})
```
