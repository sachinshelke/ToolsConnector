# Project Management

Connectors for issue tracking and project management platforms. 4 connectors, 110 actions.

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

**Category:** Project Management | **Auth:** API Key | **Actions:** 8

Connect to Linear to manage issues, teams, and projects through the GraphQL API.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_issues | List issues with optional filters | No |
| get_issue | Get details of a specific issue | No |
| create_issue | Create a new issue | Yes |
| update_issue | Update an existing issue | No |
| list_teams | List teams in the workspace | No |
| list_projects | List projects in the workspace | No |
| add_comment | Add a comment to an issue | Yes |
| search_issues | Search issues by text query | No |

**Quick start:**

```python
kit = ToolKit(["linear"], credentials={"linear": "lin_api_your-api-key"})
result = kit.execute("linear_list_issues", {"team_id": "TEAM-ID", "state": "In Progress"})
```

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
