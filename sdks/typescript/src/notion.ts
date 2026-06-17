// AUTO-GENERATED from the production connector binding. Do not edit by hand.
// Regenerate: .venv/bin/python scripts/gen_sdks.py
import { execute } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";

export const NOTION_BINDING: ConnectorB = {
  "name": "notion",
  "endpoints": {
    "main": {
      "id": "main",
      "baseUrl": "https://api.notion.com/v1",
      "encoding": "json",
      "authKind": "bearer",
      "authHeader": "Authorization",
      "extraHeaders": {
        "Notion-Version": "2022-06-28"
      }
    }
  },
  "defaultEndpoint": "main",
  "actions": {
    "get_page": {
      "name": "get_page",
      "method": "GET",
      "endpoint": "main",
      "path": "/pages/{page_id}",
      "params": [
        {
          "name": "page_id",
          "wire": "page_id",
          "location": "path",
          "required": true
        }
      ]
    },
    "update_page": {
      "name": "update_page",
      "method": "PATCH",
      "endpoint": "main",
      "path": "/pages/{page_id}",
      "params": [
        {
          "name": "page_id",
          "wire": "page_id",
          "location": "path",
          "required": true
        },
        {
          "name": "properties",
          "wire": "properties",
          "location": "body",
          "required": true
        }
      ]
    },
    "archive_page": {
      "name": "archive_page",
      "method": "PATCH",
      "endpoint": "main",
      "path": "/pages/{page_id}",
      "params": [
        {
          "name": "page_id",
          "wire": "page_id",
          "location": "path",
          "required": true
        },
        {
          "name": "archived",
          "wire": "archived",
          "location": "body",
          "default": true
        }
      ]
    },
    "restore_page": {
      "name": "restore_page",
      "method": "PATCH",
      "endpoint": "main",
      "path": "/pages/{page_id}",
      "params": [
        {
          "name": "page_id",
          "wire": "page_id",
          "location": "path",
          "required": true
        },
        {
          "name": "archived",
          "wire": "archived",
          "location": "body",
          "default": false
        }
      ]
    },
    "get_page_property": {
      "name": "get_page_property",
      "method": "GET",
      "endpoint": "main",
      "path": "/pages/{page_id}/properties/{property_id}",
      "params": [
        {
          "name": "page_id",
          "wire": "page_id",
          "location": "path",
          "required": true
        },
        {
          "name": "property_id",
          "wire": "property_id",
          "location": "path",
          "required": true
        },
        {
          "name": "limit",
          "wire": "page_size",
          "location": "query",
          "default": 100,
          "min": 1,
          "max": 100
        },
        {
          "name": "cursor",
          "wire": "start_cursor",
          "location": "query"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "results",
        "tokenField": "next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "get_database": {
      "name": "get_database",
      "method": "GET",
      "endpoint": "main",
      "path": "/databases/{database_id}",
      "params": [
        {
          "name": "database_id",
          "wire": "database_id",
          "location": "path",
          "required": true
        }
      ]
    },
    "query_database": {
      "name": "query_database",
      "method": "POST",
      "endpoint": "main",
      "path": "/databases/{database_id}/query",
      "params": [
        {
          "name": "database_id",
          "wire": "database_id",
          "location": "path",
          "required": true
        },
        {
          "name": "limit",
          "wire": "page_size",
          "location": "body",
          "default": 50,
          "min": 1,
          "max": 100
        },
        {
          "name": "filter",
          "wire": "filter",
          "location": "body"
        },
        {
          "name": "sorts",
          "wire": "sorts",
          "location": "body"
        },
        {
          "name": "cursor",
          "wire": "start_cursor",
          "location": "body"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "results",
        "tokenField": "next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "create_database": {
      "name": "create_database",
      "method": "POST",
      "endpoint": "main",
      "path": "/databases",
      "params": [
        {
          "name": "parent_id",
          "wire": "parent",
          "location": "body",
          "required": true,
          "wrap": "object",
          "wrapKey": "page_id"
        },
        {
          "name": "title",
          "wire": "title",
          "location": "body",
          "required": true,
          "wrap": "rich_text"
        },
        {
          "name": "properties",
          "wire": "properties",
          "location": "body",
          "required": true
        }
      ]
    },
    "update_database": {
      "name": "update_database",
      "method": "PATCH",
      "endpoint": "main",
      "path": "/databases/{database_id}",
      "params": [
        {
          "name": "database_id",
          "wire": "database_id",
          "location": "path",
          "required": true
        },
        {
          "name": "title",
          "wire": "title",
          "location": "body",
          "wrap": "rich_text"
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body",
          "wrap": "rich_text"
        },
        {
          "name": "properties",
          "wire": "properties",
          "location": "body"
        }
      ]
    },
    "get_block": {
      "name": "get_block",
      "method": "GET",
      "endpoint": "main",
      "path": "/blocks/{block_id}",
      "params": [
        {
          "name": "block_id",
          "wire": "block_id",
          "location": "path",
          "required": true
        }
      ]
    },
    "get_block_children": {
      "name": "get_block_children",
      "method": "GET",
      "endpoint": "main",
      "path": "/blocks/{block_id}/children",
      "params": [
        {
          "name": "block_id",
          "wire": "block_id",
          "location": "path",
          "required": true
        },
        {
          "name": "limit",
          "wire": "page_size",
          "location": "query",
          "default": 50,
          "min": 1,
          "max": 100
        },
        {
          "name": "cursor",
          "wire": "start_cursor",
          "location": "query"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "results",
        "tokenField": "next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "append_block_children": {
      "name": "append_block_children",
      "method": "PATCH",
      "endpoint": "main",
      "path": "/blocks/{block_id}/children",
      "params": [
        {
          "name": "block_id",
          "wire": "block_id",
          "location": "path",
          "required": true
        },
        {
          "name": "children",
          "wire": "children",
          "location": "body",
          "required": true
        }
      ]
    },
    "update_block": {
      "name": "update_block",
      "method": "PATCH",
      "endpoint": "main",
      "path": "/blocks/{block_id}",
      "params": [
        {
          "name": "block_id",
          "wire": "block_id",
          "location": "path",
          "required": true
        }
      ],
      "rawBodyParam": "content"
    },
    "delete_block": {
      "name": "delete_block",
      "method": "DELETE",
      "endpoint": "main",
      "path": "/blocks/{block_id}",
      "params": [
        {
          "name": "block_id",
          "wire": "block_id",
          "location": "path",
          "required": true
        }
      ]
    },
    "list_users": {
      "name": "list_users",
      "method": "GET",
      "endpoint": "main",
      "path": "/users",
      "params": []
    },
    "get_user": {
      "name": "get_user",
      "method": "GET",
      "endpoint": "main",
      "path": "/users/{user_id}",
      "params": [
        {
          "name": "user_id",
          "wire": "user_id",
          "location": "path",
          "required": true
        }
      ]
    },
    "get_me": {
      "name": "get_me",
      "method": "GET",
      "endpoint": "main",
      "path": "/users/me",
      "params": []
    },
    "list_comments": {
      "name": "list_comments",
      "method": "GET",
      "endpoint": "main",
      "path": "/comments",
      "params": [
        {
          "name": "block_id",
          "wire": "block_id",
          "location": "query",
          "required": true
        },
        {
          "name": "limit",
          "wire": "page_size",
          "location": "query",
          "default": 50,
          "min": 1,
          "max": 100
        },
        {
          "name": "cursor",
          "wire": "start_cursor",
          "location": "query"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "results",
        "tokenField": "next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "get_comment": {
      "name": "get_comment",
      "method": "GET",
      "endpoint": "main",
      "path": "/comments/{comment_id}",
      "params": [
        {
          "name": "comment_id",
          "wire": "comment_id",
          "location": "path",
          "required": true
        }
      ]
    },
    "update_comment": {
      "name": "update_comment",
      "method": "PATCH",
      "endpoint": "main",
      "path": "/comments/{comment_id}",
      "params": [
        {
          "name": "comment_id",
          "wire": "comment_id",
          "location": "path",
          "required": true
        },
        {
          "name": "text",
          "wire": "rich_text",
          "location": "body",
          "required": true,
          "wrap": "rich_text"
        }
      ]
    },
    "delete_comment": {
      "name": "delete_comment",
      "method": "DELETE",
      "endpoint": "main",
      "path": "/comments/{comment_id}",
      "params": [
        {
          "name": "comment_id",
          "wire": "comment_id",
          "location": "path",
          "required": true
        }
      ]
    }
  },
  "escapeHatches": [
    "search",
    "create_page",
    "add_comment"
  ]
};

export interface GetPageArgs {
  page_id: string;
}

export interface UpdatePageArgs {
  page_id: string;
  properties: Record<string, unknown>;
}

export interface ArchivePageArgs {
  page_id: string;
  archived?: boolean;
}

export interface RestorePageArgs {
  page_id: string;
  archived?: boolean;
}

export interface GetPagePropertyArgs {
  page_id: string;
  property_id: string;
  limit?: number;
  cursor?: string;
}

export interface GetDatabaseArgs {
  database_id: string;
}

export interface QueryDatabaseArgs {
  database_id: string;
  limit?: number;
  filter?: Record<string, unknown>;
  sorts?: Array<Record<string, unknown>>;
  cursor?: string;
}

export interface CreateDatabaseArgs {
  parent_id: string;
  title: string;
  properties: Record<string, unknown>;
}

export interface UpdateDatabaseArgs {
  database_id: string;
  title?: string;
  description?: string;
  properties?: Record<string, unknown>;
}

export interface GetBlockArgs {
  block_id: string;
}

export interface GetBlockChildrenArgs {
  block_id: string;
  limit?: number;
  cursor?: string;
}

export interface AppendBlockChildrenArgs {
  block_id: string;
  children: Array<Record<string, unknown>>;
}

export interface UpdateBlockArgs {
  block_id: string;
  content: Record<string, unknown>;
}

export interface DeleteBlockArgs {
  block_id: string;
}

export interface ListUsersArgs {
}

export interface GetUserArgs {
  user_id: string;
}

export interface GetMeArgs {
}

export interface ListCommentsArgs {
  block_id: string;
  limit?: number;
  cursor?: string;
}

export interface GetCommentArgs {
  comment_id: string;
}

export interface UpdateCommentArgs {
  comment_id: string;
  text: string;
}

export interface DeleteCommentArgs {
  comment_id: string;
}

export class Notion {
  credential: string;
  overrides: Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>>;
  constructor(credential: string, opts?: { overrides?: Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>> }) { this.credential = credential; this.overrides = opts?.overrides ?? {}; }
  /** GET /pages/{page_id} */
  async getPage(args: GetPageArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "get_page", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PATCH /pages/{page_id} */
  async updatePage(args: UpdatePageArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "update_page", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PATCH /pages/{page_id} */
  async archivePage(args: ArchivePageArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "archive_page", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PATCH /pages/{page_id} */
  async restorePage(args: RestorePageArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "restore_page", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /pages/{page_id}/properties/{property_id} */
  async getPageProperty(args: GetPagePropertyArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "get_page_property", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /databases/{database_id} */
  async getDatabase(args: GetDatabaseArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "get_database", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /databases/{database_id}/query */
  async queryDatabase(args: QueryDatabaseArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "query_database", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /databases */
  async createDatabase(args: CreateDatabaseArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "create_database", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PATCH /databases/{database_id} */
  async updateDatabase(args: UpdateDatabaseArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "update_database", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /blocks/{block_id} */
  async getBlock(args: GetBlockArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "get_block", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /blocks/{block_id}/children */
  async getBlockChildren(args: GetBlockChildrenArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "get_block_children", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PATCH /blocks/{block_id}/children */
  async appendBlockChildren(args: AppendBlockChildrenArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "append_block_children", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PATCH /blocks/{block_id} */
  async updateBlock(args: UpdateBlockArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "update_block", args as unknown as Record<string, unknown>, this.credential);
  }
  /** DELETE /blocks/{block_id} */
  async deleteBlock(args: DeleteBlockArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "delete_block", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /users */
  async listUsers(args: ListUsersArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "list_users", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /users/{user_id} */
  async getUser(args: GetUserArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "get_user", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /users/me */
  async getMe(args: GetMeArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "get_me", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /comments */
  async listComments(args: ListCommentsArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "list_comments", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /comments/{comment_id} */
  async getComment(args: GetCommentArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "get_comment", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PATCH /comments/{comment_id} */
  async updateComment(args: UpdateCommentArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "update_comment", args as unknown as Record<string, unknown>, this.credential);
  }
  /** DELETE /comments/{comment_id} */
  async deleteComment(args: DeleteCommentArgs): Promise<unknown> {
    return execute(NOTION_BINDING, "delete_comment", args as unknown as Record<string, unknown>, this.credential);
  }
  /** ESCAPE HATCH — provide via new Notion(cred, { overrides }). */
  async search(args: Record<string, unknown>): Promise<unknown> {
    const fn = this.overrides["search"];
    if (!fn) throw new Error("notion.search is an escape-hatch action; pass an override");
    return fn(this.credential, args);
  }
  /** ESCAPE HATCH — provide via new Notion(cred, { overrides }). */
  async createPage(args: Record<string, unknown>): Promise<unknown> {
    const fn = this.overrides["create_page"];
    if (!fn) throw new Error("notion.create_page is an escape-hatch action; pass an override");
    return fn(this.credential, args);
  }
  /** ESCAPE HATCH — provide via new Notion(cred, { overrides }). */
  async addComment(args: Record<string, unknown>): Promise<unknown> {
    const fn = this.overrides["add_comment"];
    if (!fn) throw new Error("notion.add_comment is an escape-hatch action; pass an override");
    return fn(this.credential, args);
  }
}
