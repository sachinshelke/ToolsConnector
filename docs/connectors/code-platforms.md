# Code Platforms

Connectors for source code hosting and collaboration platforms. 2 connectors, 18 actions.

---

### GitHub

**Category:** Code Platforms | **Auth:** Personal Access Token | **Actions:** 10

Connect to GitHub to manage repositories, issues, pull requests, and search code.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_repos | List repositories for the authenticated user | No |
| get_repo | Get details of a specific repository | No |
| list_issues | List issues in a repository | No |
| create_issue | Create a new issue | Yes |
| get_issue | Get details of a specific issue | No |
| create_comment | Create a comment on an issue or PR | Yes |
| list_pull_requests | List pull requests in a repository | No |
| get_pull_request | Get details of a specific pull request | No |
| list_commits | List commits in a repository | No |
| search_code | Search code across repositories | No |

**Quick start:**

```python
kit = ToolKit(["github"], credentials={"github": "ghp_your-personal-access-token"})
result = kit.execute("github_list_issues", {"owner": "anthropics", "repo": "toolsconnector", "state": "open"})
```

---

### GitLab

**Category:** Code Platforms | **Auth:** Personal Access Token | **Actions:** 8

Connect to GitLab to manage projects, issues, merge requests, and CI/CD pipelines.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_projects | List projects accessible to the user | No |
| get_project | Get details of a specific project | No |
| list_issues | List issues in a project | No |
| create_issue | Create a new issue | Yes |
| list_merge_requests | List merge requests in a project | No |
| create_merge_request | Create a new merge request | Yes |
| list_pipelines | List CI/CD pipelines in a project | No |
| get_pipeline | Get details of a specific pipeline | No |

**Quick start:**

```python
kit = ToolKit(["gitlab"], credentials={"gitlab": "glpat-your-access-token"})
result = kit.execute("gitlab_list_projects", {"owned": True})
```
