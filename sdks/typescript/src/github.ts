// AUTO-GENERATED from the production connector binding. Do not edit by hand.
// Regenerate: .venv/bin/python scripts/gen_sdks.py
import { execute } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";

export const GITHUB_BINDING: ConnectorB = {
  "name": "github",
  "endpoints": {
    "main": {
      "id": "main",
      "baseUrl": "https://api.github.com",
      "encoding": "json",
      "authKind": "bearer",
      "authHeader": "Authorization",
      "extraHeaders": {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
      }
    }
  },
  "defaultEndpoint": "main",
  "actions": {
    "list_repos": {
      "name": "list_repos",
      "method": "GET",
      "endpoint": "main",
      "path": "/user/repos",
      "params": [
        {
          "name": "org",
          "wire": "org",
          "location": "path"
        },
        {
          "name": "user",
          "wire": "user",
          "location": "path"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pathVariants": [
        {
          "whenPresent": "org",
          "path": "/orgs/{org}/repos"
        },
        {
          "whenPresent": "user",
          "path": "/users/{user}/repos"
        }
      ],
      "pagination": {
        "kind": "link_follow"
      }
    },
    "get_repo": {
      "name": "get_repo",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        }
      ]
    },
    "create_repo": {
      "name": "create_repo",
      "method": "POST",
      "endpoint": "main",
      "path": "/user/repos",
      "params": [
        {
          "name": "org",
          "wire": "org",
          "location": "path"
        },
        {
          "name": "name",
          "wire": "name",
          "location": "body",
          "required": true
        },
        {
          "name": "private",
          "wire": "private",
          "location": "body",
          "default": false
        },
        {
          "name": "auto_init",
          "wire": "auto_init",
          "location": "body",
          "default": false
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body"
        }
      ],
      "pathVariants": [
        {
          "whenPresent": "org",
          "path": "/orgs/{org}/repos"
        }
      ]
    },
    "fork_repo": {
      "name": "fork_repo",
      "method": "POST",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/forks",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "organization",
          "wire": "organization",
          "location": "body"
        }
      ]
    },
    "list_issues": {
      "name": "list_issues",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/issues",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "state",
          "wire": "state",
          "location": "query"
        },
        {
          "name": "labels",
          "wire": "labels",
          "location": "query"
        },
        {
          "name": "assignee",
          "wire": "assignee",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pagination": {
        "kind": "link_follow"
      }
    },
    "create_issue": {
      "name": "create_issue",
      "method": "POST",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/issues",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "title",
          "wire": "title",
          "location": "body",
          "required": true
        },
        {
          "name": "body",
          "wire": "body",
          "location": "body"
        },
        {
          "name": "labels",
          "wire": "labels",
          "location": "body"
        },
        {
          "name": "assignees",
          "wire": "assignees",
          "location": "body"
        }
      ]
    },
    "get_issue": {
      "name": "get_issue",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/issues/{issue_number}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "issue_number",
          "wire": "issue_number",
          "location": "path"
        }
      ]
    },
    "update_issue": {
      "name": "update_issue",
      "method": "PATCH",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/issues/{issue_number}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "issue_number",
          "wire": "issue_number",
          "location": "path"
        },
        {
          "name": "title",
          "wire": "title",
          "location": "body"
        },
        {
          "name": "body",
          "wire": "body",
          "location": "body"
        },
        {
          "name": "state",
          "wire": "state",
          "location": "body"
        },
        {
          "name": "labels",
          "wire": "labels",
          "location": "body"
        },
        {
          "name": "assignees",
          "wire": "assignees",
          "location": "body"
        }
      ]
    },
    "add_labels": {
      "name": "add_labels",
      "method": "POST",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/issues/{issue_number}/labels",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "issue_number",
          "wire": "issue_number",
          "location": "path"
        },
        {
          "name": "labels",
          "wire": "labels",
          "location": "body",
          "required": true
        }
      ]
    },
    "remove_label": {
      "name": "remove_label",
      "method": "DELETE",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/issues/{issue_number}/labels/{label_name}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "issue_number",
          "wire": "issue_number",
          "location": "path"
        },
        {
          "name": "label_name",
          "wire": "label_name",
          "location": "path"
        }
      ]
    },
    "create_comment": {
      "name": "create_comment",
      "method": "POST",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/issues/{issue_number}/comments",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "issue_number",
          "wire": "issue_number",
          "location": "path"
        },
        {
          "name": "body",
          "wire": "body",
          "location": "body",
          "required": true
        }
      ]
    },
    "list_comments": {
      "name": "list_comments",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/issues/{issue_number}/comments",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "issue_number",
          "wire": "issue_number",
          "location": "path"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pagination": {
        "kind": "link_follow"
      }
    },
    "list_pull_requests": {
      "name": "list_pull_requests",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/pulls",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "state",
          "wire": "state",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pagination": {
        "kind": "link_follow"
      }
    },
    "get_pull_request": {
      "name": "get_pull_request",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/pulls/{pr_number}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "pr_number",
          "wire": "pr_number",
          "location": "path"
        }
      ]
    },
    "create_pull_request": {
      "name": "create_pull_request",
      "method": "POST",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/pulls",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "title",
          "wire": "title",
          "location": "body",
          "required": true
        },
        {
          "name": "head",
          "wire": "head",
          "location": "body",
          "required": true
        },
        {
          "name": "base",
          "wire": "base",
          "location": "body",
          "required": true
        },
        {
          "name": "body",
          "wire": "body",
          "location": "body"
        },
        {
          "name": "draft",
          "wire": "draft",
          "location": "body",
          "default": false
        }
      ]
    },
    "merge_pull_request": {
      "name": "merge_pull_request",
      "method": "PUT",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/pulls/{pr_number}/merge",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "pr_number",
          "wire": "pr_number",
          "location": "path"
        },
        {
          "name": "merge_method",
          "wire": "merge_method",
          "location": "body",
          "default": "merge"
        },
        {
          "name": "commit_title",
          "wire": "commit_title",
          "location": "body"
        },
        {
          "name": "commit_message",
          "wire": "commit_message",
          "location": "body"
        }
      ]
    },
    "list_commits": {
      "name": "list_commits",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/commits",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "sha",
          "wire": "sha",
          "location": "query"
        },
        {
          "name": "path",
          "wire": "path",
          "location": "query"
        },
        {
          "name": "author",
          "wire": "author",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pagination": {
        "kind": "link_follow"
      }
    },
    "list_branches": {
      "name": "list_branches",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/branches",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pagination": {
        "kind": "link_follow"
      }
    },
    "get_branch": {
      "name": "get_branch",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/branches/{branch}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "branch",
          "wire": "branch",
          "location": "path"
        }
      ]
    },
    "list_releases": {
      "name": "list_releases",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/releases",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pagination": {
        "kind": "link_follow"
      }
    },
    "get_latest_release": {
      "name": "get_latest_release",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/releases/latest",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        }
      ]
    },
    "create_release": {
      "name": "create_release",
      "method": "POST",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/releases",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "tag_name",
          "wire": "tag_name",
          "location": "body",
          "required": true
        },
        {
          "name": "draft",
          "wire": "draft",
          "location": "body",
          "default": false
        },
        {
          "name": "prerelease",
          "wire": "prerelease",
          "location": "body",
          "default": false
        },
        {
          "name": "name",
          "wire": "name",
          "location": "body"
        },
        {
          "name": "body",
          "wire": "body",
          "location": "body"
        },
        {
          "name": "target_commitish",
          "wire": "target_commitish",
          "location": "body"
        }
      ]
    },
    "get_content": {
      "name": "get_content",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/contents/{path}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "path",
          "wire": "path",
          "location": "path"
        },
        {
          "name": "ref",
          "wire": "ref",
          "location": "query"
        }
      ]
    },
    "create_or_update_file": {
      "name": "create_or_update_file",
      "method": "PUT",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/contents/{path}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "path",
          "wire": "path",
          "location": "path"
        },
        {
          "name": "message",
          "wire": "message",
          "location": "body",
          "required": true
        },
        {
          "name": "content",
          "wire": "content",
          "location": "body",
          "required": true
        },
        {
          "name": "sha",
          "wire": "sha",
          "location": "body"
        },
        {
          "name": "branch",
          "wire": "branch",
          "location": "body"
        }
      ]
    },
    "delete_file": {
      "name": "delete_file",
      "method": "DELETE",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/contents/{path}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "path",
          "wire": "path",
          "location": "path"
        },
        {
          "name": "message",
          "wire": "message",
          "location": "body",
          "required": true
        },
        {
          "name": "sha",
          "wire": "sha",
          "location": "body",
          "required": true
        },
        {
          "name": "branch",
          "wire": "branch",
          "location": "body"
        }
      ]
    },
    "list_workflows": {
      "name": "list_workflows",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/actions/workflows",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "unwrap": "workflows",
      "pagination": {
        "kind": "link_follow",
        "itemsField": "workflows"
      }
    },
    "list_workflow_runs": {
      "name": "list_workflow_runs",
      "method": "GET",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/actions/runs",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "workflow_id",
          "wire": "workflow_id",
          "location": "path"
        },
        {
          "name": "branch",
          "wire": "branch",
          "location": "query"
        },
        {
          "name": "status",
          "wire": "status",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pathVariants": [
        {
          "whenPresent": "workflow_id",
          "path": "/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        }
      ],
      "unwrap": "workflow_runs",
      "pagination": {
        "kind": "link_follow",
        "itemsField": "workflow_runs"
      }
    },
    "trigger_workflow": {
      "name": "trigger_workflow",
      "method": "POST",
      "endpoint": "main",
      "path": "/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        },
        {
          "name": "workflow_id",
          "wire": "workflow_id",
          "location": "path"
        },
        {
          "name": "ref",
          "wire": "ref",
          "location": "body",
          "default": "main"
        },
        {
          "name": "inputs",
          "wire": "inputs",
          "location": "body"
        }
      ]
    },
    "list_gists": {
      "name": "list_gists",
      "method": "GET",
      "endpoint": "main",
      "path": "/gists",
      "params": [
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "pagination": {
        "kind": "link_follow"
      }
    },
    "search_code": {
      "name": "search_code",
      "method": "GET",
      "endpoint": "main",
      "path": "/search/code",
      "params": [
        {
          "name": "query",
          "wire": "q",
          "location": "query",
          "required": true
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "unwrap": "items",
      "pagination": {
        "kind": "link_follow",
        "itemsField": "items"
      }
    },
    "search_repos": {
      "name": "search_repos",
      "method": "GET",
      "endpoint": "main",
      "path": "/search/repositories",
      "params": [
        {
          "name": "query",
          "wire": "q",
          "location": "query",
          "required": true
        },
        {
          "name": "order",
          "wire": "order",
          "location": "query",
          "default": "desc"
        },
        {
          "name": "sort",
          "wire": "sort",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "unwrap": "items",
      "pagination": {
        "kind": "link_follow",
        "itemsField": "items"
      }
    },
    "search_issues": {
      "name": "search_issues",
      "method": "GET",
      "endpoint": "main",
      "path": "/search/issues",
      "params": [
        {
          "name": "query",
          "wire": "q",
          "location": "query",
          "required": true
        },
        {
          "name": "order",
          "wire": "order",
          "location": "query",
          "default": "desc"
        },
        {
          "name": "sort",
          "wire": "sort",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "per_page",
          "location": "query",
          "default": 30,
          "max": 100
        }
      ],
      "unwrap": "items",
      "pagination": {
        "kind": "link_follow",
        "itemsField": "items"
      }
    },
    "get_authenticated_user": {
      "name": "get_authenticated_user",
      "method": "GET",
      "endpoint": "main",
      "path": "/user",
      "params": []
    },
    "get_rate_limit": {
      "name": "get_rate_limit",
      "method": "GET",
      "endpoint": "main",
      "path": "/rate_limit",
      "params": []
    },
    "star_repo": {
      "name": "star_repo",
      "method": "PUT",
      "endpoint": "main",
      "path": "/user/starred/{owner}/{repo}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        }
      ]
    },
    "unstar_repo": {
      "name": "unstar_repo",
      "method": "DELETE",
      "endpoint": "main",
      "path": "/user/starred/{owner}/{repo}",
      "params": [
        {
          "name": "owner",
          "wire": "owner",
          "location": "path"
        },
        {
          "name": "repo",
          "wire": "repo",
          "location": "path"
        }
      ]
    }
  },
  "escapeHatches": [
    "create_gist"
  ]
};

export interface ListReposArgs {
  org?: string;
  user?: string;
  limit?: number;
}

export interface GetRepoArgs {
  owner: string;
  repo: string;
}

export interface CreateRepoArgs {
  org?: string;
  name: string;
  private?: boolean;
  auto_init?: boolean;
  description?: string;
}

export interface ForkRepoArgs {
  owner: string;
  repo: string;
  organization?: string;
}

export interface ListIssuesArgs {
  owner: string;
  repo: string;
  state?: string;
  labels?: string;
  assignee?: string;
  limit?: number;
}

export interface CreateIssueArgs {
  owner: string;
  repo: string;
  title: string;
  body?: string;
  labels?: string[];
  assignees?: string[];
}

export interface GetIssueArgs {
  owner: string;
  repo: string;
  issue_number: string;
}

export interface UpdateIssueArgs {
  owner: string;
  repo: string;
  issue_number: string;
  title?: string;
  body?: string;
  state?: string;
  labels?: string[];
  assignees?: string[];
}

export interface AddLabelsArgs {
  owner: string;
  repo: string;
  issue_number: string;
  labels: string[];
}

export interface RemoveLabelArgs {
  owner: string;
  repo: string;
  issue_number: string;
  label_name: string;
}

export interface CreateCommentArgs {
  owner: string;
  repo: string;
  issue_number: string;
  body: string;
}

export interface ListCommentsArgs {
  owner: string;
  repo: string;
  issue_number: string;
  limit?: number;
}

export interface ListPullRequestsArgs {
  owner: string;
  repo: string;
  state?: string;
  limit?: number;
}

export interface GetPullRequestArgs {
  owner: string;
  repo: string;
  pr_number: string;
}

export interface CreatePullRequestArgs {
  owner: string;
  repo: string;
  title: string;
  head: string;
  base: string;
  body?: string;
  draft?: boolean;
}

export interface MergePullRequestArgs {
  owner: string;
  repo: string;
  pr_number: string;
  merge_method?: string;
  commit_title?: string;
  commit_message?: string;
}

export interface ListCommitsArgs {
  owner: string;
  repo: string;
  sha?: string;
  path?: string;
  author?: string;
  limit?: number;
}

export interface ListBranchesArgs {
  owner: string;
  repo: string;
  limit?: number;
}

export interface GetBranchArgs {
  owner: string;
  repo: string;
  branch: string;
}

export interface ListReleasesArgs {
  owner: string;
  repo: string;
  limit?: number;
}

export interface GetLatestReleaseArgs {
  owner: string;
  repo: string;
}

export interface CreateReleaseArgs {
  owner: string;
  repo: string;
  tag_name: string;
  draft?: boolean;
  prerelease?: boolean;
  name?: string;
  body?: string;
  target_commitish?: string;
}

export interface GetContentArgs {
  owner: string;
  repo: string;
  path: string;
  ref?: string;
}

export interface CreateOrUpdateFileArgs {
  owner: string;
  repo: string;
  path: string;
  message: string;
  content: string;
  sha?: string;
  branch?: string;
}

export interface DeleteFileArgs {
  owner: string;
  repo: string;
  path: string;
  message: string;
  sha: string;
  branch?: string;
}

export interface ListWorkflowsArgs {
  owner: string;
  repo: string;
  limit?: number;
}

export interface ListWorkflowRunsArgs {
  owner: string;
  repo: string;
  workflow_id?: string;
  branch?: string;
  status?: string;
  limit?: number;
}

export interface TriggerWorkflowArgs {
  owner: string;
  repo: string;
  workflow_id: string;
  ref?: string;
  inputs?: Record<string, unknown>;
}

export interface ListGistsArgs {
  limit?: number;
}

export interface SearchCodeArgs {
  query: string;
  limit?: number;
}

export interface SearchReposArgs {
  query: string;
  order?: string;
  sort?: string;
  limit?: number;
}

export interface SearchIssuesArgs {
  query: string;
  order?: string;
  sort?: string;
  limit?: number;
}

export interface GetAuthenticatedUserArgs {
}

export interface GetRateLimitArgs {
}

export interface StarRepoArgs {
  owner: string;
  repo: string;
}

export interface UnstarRepoArgs {
  owner: string;
  repo: string;
}

export class Github {
  credential: string;
  overrides: Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>>;
  constructor(credential: string, opts?: { overrides?: Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>> }) { this.credential = credential; this.overrides = opts?.overrides ?? {}; }
  /** GET /user/repos */
  async listRepos(args: ListReposArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_repos", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo} */
  async getRepo(args: GetRepoArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "get_repo", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /user/repos */
  async createRepo(args: CreateRepoArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "create_repo", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /repos/{owner}/{repo}/forks */
  async forkRepo(args: ForkRepoArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "fork_repo", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/issues */
  async listIssues(args: ListIssuesArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_issues", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /repos/{owner}/{repo}/issues */
  async createIssue(args: CreateIssueArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "create_issue", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/issues/{issue_number} */
  async getIssue(args: GetIssueArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "get_issue", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PATCH /repos/{owner}/{repo}/issues/{issue_number} */
  async updateIssue(args: UpdateIssueArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "update_issue", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /repos/{owner}/{repo}/issues/{issue_number}/labels */
  async addLabels(args: AddLabelsArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "add_labels", args as unknown as Record<string, unknown>, this.credential);
  }
  /** DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{label_name} */
  async removeLabel(args: RemoveLabelArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "remove_label", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /repos/{owner}/{repo}/issues/{issue_number}/comments */
  async createComment(args: CreateCommentArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "create_comment", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/issues/{issue_number}/comments */
  async listComments(args: ListCommentsArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_comments", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/pulls */
  async listPullRequests(args: ListPullRequestsArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_pull_requests", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/pulls/{pr_number} */
  async getPullRequest(args: GetPullRequestArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "get_pull_request", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /repos/{owner}/{repo}/pulls */
  async createPullRequest(args: CreatePullRequestArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "create_pull_request", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PUT /repos/{owner}/{repo}/pulls/{pr_number}/merge */
  async mergePullRequest(args: MergePullRequestArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "merge_pull_request", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/commits */
  async listCommits(args: ListCommitsArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_commits", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/branches */
  async listBranches(args: ListBranchesArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_branches", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/branches/{branch} */
  async getBranch(args: GetBranchArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "get_branch", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/releases */
  async listReleases(args: ListReleasesArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_releases", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/releases/latest */
  async getLatestRelease(args: GetLatestReleaseArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "get_latest_release", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /repos/{owner}/{repo}/releases */
  async createRelease(args: CreateReleaseArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "create_release", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/contents/{path} */
  async getContent(args: GetContentArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "get_content", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PUT /repos/{owner}/{repo}/contents/{path} */
  async createOrUpdateFile(args: CreateOrUpdateFileArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "create_or_update_file", args as unknown as Record<string, unknown>, this.credential);
  }
  /** DELETE /repos/{owner}/{repo}/contents/{path} */
  async deleteFile(args: DeleteFileArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "delete_file", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/actions/workflows */
  async listWorkflows(args: ListWorkflowsArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_workflows", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /repos/{owner}/{repo}/actions/runs */
  async listWorkflowRuns(args: ListWorkflowRunsArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_workflow_runs", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches */
  async triggerWorkflow(args: TriggerWorkflowArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "trigger_workflow", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /gists */
  async listGists(args: ListGistsArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "list_gists", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /search/code */
  async searchCode(args: SearchCodeArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "search_code", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /search/repositories */
  async searchRepos(args: SearchReposArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "search_repos", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /search/issues */
  async searchIssues(args: SearchIssuesArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "search_issues", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /user */
  async getAuthenticatedUser(args: GetAuthenticatedUserArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "get_authenticated_user", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /rate_limit */
  async getRateLimit(args: GetRateLimitArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "get_rate_limit", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PUT /user/starred/{owner}/{repo} */
  async starRepo(args: StarRepoArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "star_repo", args as unknown as Record<string, unknown>, this.credential);
  }
  /** DELETE /user/starred/{owner}/{repo} */
  async unstarRepo(args: UnstarRepoArgs): Promise<unknown> {
    return execute(GITHUB_BINDING, "unstar_repo", args as unknown as Record<string, unknown>, this.credential);
  }
  /** ESCAPE HATCH — provide via new Github(cred, { overrides }). */
  async createGist(args: Record<string, unknown>): Promise<unknown> {
    const fn = this.overrides["create_gist"];
    if (!fn) throw new Error("github.create_gist is an escape-hatch action; pass an override");
    return fn(this.credential, args);
  }
}
