// AUTO-GENERATED from the production connector binding. Do not edit by hand.
// Regenerate: .venv/bin/python scripts/gen_sdks.py
import { execute } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";

export const SLACK_BINDING: ConnectorB = {
  "name": "slack",
  "endpoints": {
    "main": {
      "id": "main",
      "baseUrl": "https://slack.com/api",
      "encoding": "json",
      "authKind": "bearer",
      "authHeader": "Authorization"
    }
  },
  "defaultEndpoint": "main",
  "actions": {
    "send_message": {
      "name": "send_message",
      "method": "POST",
      "endpoint": "main",
      "path": "chat.postMessage",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "text",
          "wire": "text",
          "location": "body",
          "required": true
        },
        {
          "name": "unfurl_links",
          "wire": "unfurl_links",
          "location": "body",
          "default": true
        },
        {
          "name": "unfurl_media",
          "wire": "unfurl_media",
          "location": "body",
          "default": true
        },
        {
          "name": "thread_ts",
          "wire": "thread_ts",
          "location": "body"
        }
      ]
    },
    "update_message": {
      "name": "update_message",
      "method": "POST",
      "endpoint": "main",
      "path": "chat.update",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "ts",
          "wire": "ts",
          "location": "body",
          "required": true
        },
        {
          "name": "text",
          "wire": "text",
          "location": "body",
          "required": true
        }
      ]
    },
    "delete_message": {
      "name": "delete_message",
      "method": "POST",
      "endpoint": "main",
      "path": "chat.delete",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "ts",
          "wire": "ts",
          "location": "body",
          "required": true
        }
      ]
    },
    "schedule_message": {
      "name": "schedule_message",
      "method": "POST",
      "endpoint": "main",
      "path": "chat.scheduleMessage",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "text",
          "wire": "text",
          "location": "body",
          "required": true
        },
        {
          "name": "post_at",
          "wire": "post_at",
          "location": "body",
          "required": true
        },
        {
          "name": "thread_ts",
          "wire": "thread_ts",
          "location": "body"
        }
      ]
    },
    "list_scheduled_messages": {
      "name": "list_scheduled_messages",
      "method": "POST",
      "endpoint": "main",
      "path": "chat.scheduledMessages.list",
      "params": [
        {
          "name": "limit",
          "wire": "limit",
          "location": "body",
          "default": 100,
          "max": 100
        },
        {
          "name": "channel",
          "wire": "channel",
          "location": "body"
        },
        {
          "name": "cursor",
          "wire": "cursor",
          "location": "body"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "scheduled_messages",
        "tokenField": "response_metadata.next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "delete_scheduled_message": {
      "name": "delete_scheduled_message",
      "method": "POST",
      "endpoint": "main",
      "path": "chat.deleteScheduledMessage",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "scheduled_message_id",
          "wire": "scheduled_message_id",
          "location": "body",
          "required": true
        }
      ]
    },
    "get_permalink": {
      "name": "get_permalink",
      "method": "GET",
      "endpoint": "main",
      "path": "chat.getPermalink",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "query",
          "required": true
        },
        {
          "name": "message_ts",
          "wire": "message_ts",
          "location": "query",
          "required": true
        }
      ]
    },
    "list_channels": {
      "name": "list_channels",
      "method": "GET",
      "endpoint": "main",
      "path": "conversations.list",
      "params": [
        {
          "name": "types",
          "wire": "types",
          "location": "query",
          "default": "public_channel,private_channel"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 100,
          "max": 1000
        },
        {
          "name": "exclude_archived",
          "wire": "exclude_archived",
          "location": "query",
          "default": false
        },
        {
          "name": "cursor",
          "wire": "cursor",
          "location": "query"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "channels",
        "tokenField": "response_metadata.next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "get_channel": {
      "name": "get_channel",
      "method": "GET",
      "endpoint": "main",
      "path": "conversations.info",
      "params": [
        {
          "name": "channel_id",
          "wire": "channel",
          "location": "query",
          "required": true
        }
      ]
    },
    "create_channel": {
      "name": "create_channel",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.create",
      "params": [
        {
          "name": "name",
          "wire": "name",
          "location": "body",
          "required": true
        },
        {
          "name": "is_private",
          "wire": "is_private",
          "location": "body",
          "default": false
        }
      ]
    },
    "archive_channel": {
      "name": "archive_channel",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.archive",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        }
      ]
    },
    "unarchive_channel": {
      "name": "unarchive_channel",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.unarchive",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        }
      ]
    },
    "rename_channel": {
      "name": "rename_channel",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.rename",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "name",
          "wire": "name",
          "location": "body",
          "required": true
        }
      ]
    },
    "set_channel_topic": {
      "name": "set_channel_topic",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.setTopic",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "topic",
          "wire": "topic",
          "location": "body",
          "required": true
        }
      ]
    },
    "set_channel_purpose": {
      "name": "set_channel_purpose",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.setPurpose",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "purpose",
          "wire": "purpose",
          "location": "body",
          "required": true
        }
      ]
    },
    "invite_to_channel": {
      "name": "invite_to_channel",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.invite",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "users",
          "wire": "users",
          "location": "body",
          "required": true
        }
      ]
    },
    "kick_from_channel": {
      "name": "kick_from_channel",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.kick",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "user",
          "wire": "user",
          "location": "body",
          "required": true
        }
      ]
    },
    "join_channel": {
      "name": "join_channel",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.join",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        }
      ]
    },
    "leave_channel": {
      "name": "leave_channel",
      "method": "POST",
      "endpoint": "main",
      "path": "conversations.leave",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        }
      ]
    },
    "list_channel_members": {
      "name": "list_channel_members",
      "method": "GET",
      "endpoint": "main",
      "path": "conversations.members",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "query",
          "required": true
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 100,
          "max": 1000
        },
        {
          "name": "cursor",
          "wire": "cursor",
          "location": "query"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "members",
        "tokenField": "response_metadata.next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "list_messages": {
      "name": "list_messages",
      "method": "GET",
      "endpoint": "main",
      "path": "conversations.history",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "query",
          "required": true
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 100,
          "max": 1000
        },
        {
          "name": "cursor",
          "wire": "cursor",
          "location": "query"
        },
        {
          "name": "oldest",
          "wire": "oldest",
          "location": "query"
        },
        {
          "name": "latest",
          "wire": "latest",
          "location": "query"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "messages",
        "tokenField": "response_metadata.next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "list_thread_replies": {
      "name": "list_thread_replies",
      "method": "GET",
      "endpoint": "main",
      "path": "conversations.replies",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "query",
          "required": true
        },
        {
          "name": "thread_ts",
          "wire": "ts",
          "location": "query",
          "required": true
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 100,
          "max": 1000
        },
        {
          "name": "cursor",
          "wire": "cursor",
          "location": "query"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "messages",
        "tokenField": "response_metadata.next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "add_reaction": {
      "name": "add_reaction",
      "method": "POST",
      "endpoint": "main",
      "path": "reactions.add",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "timestamp",
          "wire": "timestamp",
          "location": "body",
          "required": true
        },
        {
          "name": "emoji",
          "wire": "name",
          "location": "body",
          "required": true
        }
      ]
    },
    "remove_reaction": {
      "name": "remove_reaction",
      "method": "POST",
      "endpoint": "main",
      "path": "reactions.remove",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "timestamp",
          "wire": "timestamp",
          "location": "body",
          "required": true
        },
        {
          "name": "emoji",
          "wire": "name",
          "location": "body",
          "required": true
        }
      ]
    },
    "get_reactions": {
      "name": "get_reactions",
      "method": "GET",
      "endpoint": "main",
      "path": "reactions.get",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "query",
          "required": true
        },
        {
          "name": "timestamp",
          "wire": "timestamp",
          "location": "query",
          "required": true
        },
        {
          "name": "full",
          "wire": "full",
          "location": "query",
          "default": "true"
        }
      ]
    },
    "pin_message": {
      "name": "pin_message",
      "method": "POST",
      "endpoint": "main",
      "path": "pins.add",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "timestamp",
          "wire": "timestamp",
          "location": "body",
          "required": true
        }
      ]
    },
    "unpin_message": {
      "name": "unpin_message",
      "method": "POST",
      "endpoint": "main",
      "path": "pins.remove",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "body",
          "required": true
        },
        {
          "name": "timestamp",
          "wire": "timestamp",
          "location": "body",
          "required": true
        }
      ]
    },
    "list_pins": {
      "name": "list_pins",
      "method": "GET",
      "endpoint": "main",
      "path": "pins.list",
      "params": [
        {
          "name": "channel",
          "wire": "channel",
          "location": "query",
          "required": true
        }
      ]
    },
    "delete_file": {
      "name": "delete_file",
      "method": "POST",
      "endpoint": "main",
      "path": "files.delete",
      "params": [
        {
          "name": "file_id",
          "wire": "file",
          "location": "body",
          "required": true
        }
      ]
    },
    "get_file_info": {
      "name": "get_file_info",
      "method": "GET",
      "endpoint": "main",
      "path": "files.info",
      "params": [
        {
          "name": "file_id",
          "wire": "file",
          "location": "query",
          "required": true
        }
      ]
    },
    "list_users": {
      "name": "list_users",
      "method": "GET",
      "endpoint": "main",
      "path": "users.list",
      "params": [
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 100,
          "max": 1000
        },
        {
          "name": "cursor",
          "wire": "cursor",
          "location": "query"
        }
      ],
      "pagination": {
        "kind": "offset_token",
        "itemsField": "members",
        "tokenField": "response_metadata.next_cursor",
        "tokenParamPy": "cursor"
      }
    },
    "get_user": {
      "name": "get_user",
      "method": "GET",
      "endpoint": "main",
      "path": "users.info",
      "params": [
        {
          "name": "user_id",
          "wire": "user",
          "location": "query",
          "required": true
        }
      ]
    },
    "lookup_user_by_email": {
      "name": "lookup_user_by_email",
      "method": "GET",
      "endpoint": "main",
      "path": "users.lookupByEmail",
      "params": [
        {
          "name": "email",
          "wire": "email",
          "location": "query",
          "required": true
        }
      ]
    },
    "get_user_presence": {
      "name": "get_user_presence",
      "method": "GET",
      "endpoint": "main",
      "path": "users.getPresence",
      "params": [
        {
          "name": "user_id",
          "wire": "user",
          "location": "query",
          "required": true
        }
      ]
    },
    "get_user_profile": {
      "name": "get_user_profile",
      "method": "GET",
      "endpoint": "main",
      "path": "users.profile.get",
      "params": [
        {
          "name": "user_id",
          "wire": "user",
          "location": "query",
          "required": true
        }
      ]
    },
    "set_presence": {
      "name": "set_presence",
      "method": "POST",
      "endpoint": "main",
      "path": "users.setPresence",
      "params": [
        {
          "name": "presence",
          "wire": "presence",
          "location": "body",
          "required": true
        }
      ]
    },
    "search_messages": {
      "name": "search_messages",
      "method": "GET",
      "endpoint": "main",
      "path": "search.messages",
      "params": [
        {
          "name": "query",
          "wire": "query",
          "location": "query",
          "required": true
        },
        {
          "name": "sort",
          "wire": "sort",
          "location": "query",
          "default": "timestamp"
        },
        {
          "name": "sort_dir",
          "wire": "sort_dir",
          "location": "query",
          "default": "desc"
        },
        {
          "name": "count",
          "wire": "count",
          "location": "query",
          "default": 20,
          "max": 100
        },
        {
          "name": "page",
          "wire": "page",
          "location": "query",
          "default": 1
        }
      ]
    },
    "set_status": {
      "name": "set_status",
      "method": "POST",
      "endpoint": "main",
      "path": "users.profile.set",
      "params": [
        {
          "name": "status_text",
          "wire": "status_text",
          "location": "body",
          "required": true
        },
        {
          "name": "status_emoji",
          "wire": "status_emoji",
          "location": "body"
        },
        {
          "name": "expiration",
          "wire": "status_expiration",
          "location": "body"
        }
      ],
      "bodyWrap": "profile"
    },
    "add_bookmark": {
      "name": "add_bookmark",
      "method": "POST",
      "endpoint": "main",
      "path": "bookmarks.add",
      "params": [
        {
          "name": "channel_id",
          "wire": "channel_id",
          "location": "body",
          "required": true
        },
        {
          "name": "title",
          "wire": "title",
          "location": "body",
          "required": true
        },
        {
          "name": "type",
          "wire": "type",
          "location": "body",
          "default": "link"
        },
        {
          "name": "link",
          "wire": "link",
          "location": "body",
          "required": true
        },
        {
          "name": "emoji",
          "wire": "emoji",
          "location": "body"
        }
      ]
    },
    "list_bookmarks": {
      "name": "list_bookmarks",
      "method": "GET",
      "endpoint": "main",
      "path": "bookmarks.list",
      "params": [
        {
          "name": "channel_id",
          "wire": "channel_id",
          "location": "query",
          "required": true
        }
      ]
    },
    "remove_bookmark": {
      "name": "remove_bookmark",
      "method": "POST",
      "endpoint": "main",
      "path": "bookmarks.remove",
      "params": [
        {
          "name": "bookmark_id",
          "wire": "bookmark_id",
          "location": "body",
          "required": true
        },
        {
          "name": "channel_id",
          "wire": "channel_id",
          "location": "body",
          "required": true
        }
      ]
    },
    "add_reminder": {
      "name": "add_reminder",
      "method": "POST",
      "endpoint": "main",
      "path": "reminders.add",
      "params": [
        {
          "name": "text",
          "wire": "text",
          "location": "body",
          "required": true
        },
        {
          "name": "time",
          "wire": "time",
          "location": "body",
          "required": true
        },
        {
          "name": "user",
          "wire": "user",
          "location": "body"
        }
      ]
    },
    "list_reminders": {
      "name": "list_reminders",
      "method": "GET",
      "endpoint": "main",
      "path": "reminders.list",
      "params": []
    },
    "delete_reminder": {
      "name": "delete_reminder",
      "method": "POST",
      "endpoint": "main",
      "path": "reminders.delete",
      "params": [
        {
          "name": "reminder_id",
          "wire": "reminder",
          "location": "body",
          "required": true
        }
      ]
    },
    "list_emoji": {
      "name": "list_emoji",
      "method": "GET",
      "endpoint": "main",
      "path": "emoji.list",
      "params": []
    },
    "auth_test": {
      "name": "auth_test",
      "method": "POST",
      "endpoint": "main",
      "path": "auth.test",
      "params": []
    },
    "get_team_info": {
      "name": "get_team_info",
      "method": "GET",
      "endpoint": "main",
      "path": "team.info",
      "params": []
    },
    "create_usergroup": {
      "name": "create_usergroup",
      "method": "POST",
      "endpoint": "main",
      "path": "usergroups.create",
      "params": [
        {
          "name": "name",
          "wire": "name",
          "location": "body",
          "required": true
        },
        {
          "name": "handle",
          "wire": "handle",
          "location": "body",
          "required": true
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body"
        },
        {
          "name": "channels",
          "wire": "channels",
          "location": "body"
        }
      ]
    },
    "list_usergroups": {
      "name": "list_usergroups",
      "method": "GET",
      "endpoint": "main",
      "path": "usergroups.list",
      "params": [
        {
          "name": "include_users",
          "wire": "include_users",
          "location": "query",
          "default": false
        },
        {
          "name": "include_disabled",
          "wire": "include_disabled",
          "location": "query",
          "default": false
        }
      ]
    },
    "update_usergroup": {
      "name": "update_usergroup",
      "method": "POST",
      "endpoint": "main",
      "path": "usergroups.update",
      "params": [
        {
          "name": "usergroup_id",
          "wire": "usergroup",
          "location": "body",
          "required": true
        },
        {
          "name": "name",
          "wire": "name",
          "location": "body"
        },
        {
          "name": "handle",
          "wire": "handle",
          "location": "body"
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body"
        },
        {
          "name": "channels",
          "wire": "channels",
          "location": "body"
        }
      ]
    }
  },
  "escapeHatches": [
    "upload_file"
  ]
};

export interface SendMessageArgs {
  channel: string;
  text: string;
  unfurl_links?: boolean;
  unfurl_media?: boolean;
  thread_ts?: string;
}

export interface UpdateMessageArgs {
  channel: string;
  ts: string;
  text: string;
}

export interface DeleteMessageArgs {
  channel: string;
  ts: string;
}

export interface ScheduleMessageArgs {
  channel: string;
  text: string;
  post_at: number;
  thread_ts?: string;
}

export interface ListScheduledMessagesArgs {
  limit?: number;
  channel?: string;
  cursor?: string;
}

export interface DeleteScheduledMessageArgs {
  channel: string;
  scheduled_message_id: string;
}

export interface GetPermalinkArgs {
  channel: string;
  message_ts: string;
}

export interface ListChannelsArgs {
  types?: string;
  limit?: number;
  exclude_archived?: boolean;
  cursor?: string;
}

export interface GetChannelArgs {
  channel_id: string;
}

export interface CreateChannelArgs {
  name: string;
  is_private?: boolean;
}

export interface ArchiveChannelArgs {
  channel: string;
}

export interface UnarchiveChannelArgs {
  channel: string;
}

export interface RenameChannelArgs {
  channel: string;
  name: string;
}

export interface SetChannelTopicArgs {
  channel: string;
  topic: string;
}

export interface SetChannelPurposeArgs {
  channel: string;
  purpose: string;
}

export interface InviteToChannelArgs {
  channel: string;
  users: string;
}

export interface KickFromChannelArgs {
  channel: string;
  user: string;
}

export interface JoinChannelArgs {
  channel: string;
}

export interface LeaveChannelArgs {
  channel: string;
}

export interface ListChannelMembersArgs {
  channel: string;
  limit?: number;
  cursor?: string;
}

export interface ListMessagesArgs {
  channel: string;
  limit?: number;
  cursor?: string;
  oldest?: string;
  latest?: string;
}

export interface ListThreadRepliesArgs {
  channel: string;
  thread_ts: string;
  limit?: number;
  cursor?: string;
}

export interface AddReactionArgs {
  channel: string;
  timestamp: string;
  emoji: string;
}

export interface RemoveReactionArgs {
  channel: string;
  timestamp: string;
  emoji: string;
}

export interface GetReactionsArgs {
  channel: string;
  timestamp: string;
  full?: string;
}

export interface PinMessageArgs {
  channel: string;
  timestamp: string;
}

export interface UnpinMessageArgs {
  channel: string;
  timestamp: string;
}

export interface ListPinsArgs {
  channel: string;
}

export interface DeleteFileArgs {
  file_id: string;
}

export interface GetFileInfoArgs {
  file_id: string;
}

export interface ListUsersArgs {
  limit?: number;
  cursor?: string;
}

export interface GetUserArgs {
  user_id: string;
}

export interface LookupUserByEmailArgs {
  email: string;
}

export interface GetUserPresenceArgs {
  user_id: string;
}

export interface GetUserProfileArgs {
  user_id: string;
}

export interface SetPresenceArgs {
  presence: string;
}

export interface SearchMessagesArgs {
  query: string;
  sort?: string;
  sort_dir?: string;
  count?: number;
  page?: number;
}

export interface SetStatusArgs {
  status_text: string;
  status_emoji?: string;
  expiration?: number;
}

export interface AddBookmarkArgs {
  channel_id: string;
  title: string;
  type?: string;
  link: string;
  emoji?: string;
}

export interface ListBookmarksArgs {
  channel_id: string;
}

export interface RemoveBookmarkArgs {
  bookmark_id: string;
  channel_id: string;
}

export interface AddReminderArgs {
  text: string;
  time: string;
  user?: string;
}

export interface ListRemindersArgs {
}

export interface DeleteReminderArgs {
  reminder_id: string;
}

export interface ListEmojiArgs {
}

export interface AuthTestArgs {
}

export interface GetTeamInfoArgs {
}

export interface CreateUsergroupArgs {
  name: string;
  handle: string;
  description?: string;
  channels?: string;
}

export interface ListUsergroupsArgs {
  include_users?: boolean;
  include_disabled?: boolean;
}

export interface UpdateUsergroupArgs {
  usergroup_id: string;
  name?: string;
  handle?: string;
  description?: string;
  channels?: string;
}

export class Slack {
  credential: string;
  overrides: Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>>;
  constructor(credential: string, opts?: { overrides?: Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>> }) { this.credential = credential; this.overrides = opts?.overrides ?? {}; }
  /** POST chat.postMessage */
  async sendMessage(args: SendMessageArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "send_message", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST chat.update */
  async updateMessage(args: UpdateMessageArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "update_message", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST chat.delete */
  async deleteMessage(args: DeleteMessageArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "delete_message", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST chat.scheduleMessage */
  async scheduleMessage(args: ScheduleMessageArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "schedule_message", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST chat.scheduledMessages.list */
  async listScheduledMessages(args: ListScheduledMessagesArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_scheduled_messages", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST chat.deleteScheduledMessage */
  async deleteScheduledMessage(args: DeleteScheduledMessageArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "delete_scheduled_message", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET chat.getPermalink */
  async getPermalink(args: GetPermalinkArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "get_permalink", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET conversations.list */
  async listChannels(args: ListChannelsArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_channels", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET conversations.info */
  async getChannel(args: GetChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "get_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.create */
  async createChannel(args: CreateChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "create_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.archive */
  async archiveChannel(args: ArchiveChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "archive_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.unarchive */
  async unarchiveChannel(args: UnarchiveChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "unarchive_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.rename */
  async renameChannel(args: RenameChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "rename_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.setTopic */
  async setChannelTopic(args: SetChannelTopicArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "set_channel_topic", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.setPurpose */
  async setChannelPurpose(args: SetChannelPurposeArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "set_channel_purpose", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.invite */
  async inviteToChannel(args: InviteToChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "invite_to_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.kick */
  async kickFromChannel(args: KickFromChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "kick_from_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.join */
  async joinChannel(args: JoinChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "join_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST conversations.leave */
  async leaveChannel(args: LeaveChannelArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "leave_channel", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET conversations.members */
  async listChannelMembers(args: ListChannelMembersArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_channel_members", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET conversations.history */
  async listMessages(args: ListMessagesArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_messages", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET conversations.replies */
  async listThreadReplies(args: ListThreadRepliesArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_thread_replies", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST reactions.add */
  async addReaction(args: AddReactionArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "add_reaction", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST reactions.remove */
  async removeReaction(args: RemoveReactionArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "remove_reaction", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET reactions.get */
  async getReactions(args: GetReactionsArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "get_reactions", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST pins.add */
  async pinMessage(args: PinMessageArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "pin_message", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST pins.remove */
  async unpinMessage(args: UnpinMessageArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "unpin_message", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET pins.list */
  async listPins(args: ListPinsArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_pins", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST files.delete */
  async deleteFile(args: DeleteFileArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "delete_file", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET files.info */
  async getFileInfo(args: GetFileInfoArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "get_file_info", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET users.list */
  async listUsers(args: ListUsersArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_users", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET users.info */
  async getUser(args: GetUserArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "get_user", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET users.lookupByEmail */
  async lookupUserByEmail(args: LookupUserByEmailArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "lookup_user_by_email", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET users.getPresence */
  async getUserPresence(args: GetUserPresenceArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "get_user_presence", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET users.profile.get */
  async getUserProfile(args: GetUserProfileArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "get_user_profile", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST users.setPresence */
  async setPresence(args: SetPresenceArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "set_presence", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET search.messages */
  async searchMessages(args: SearchMessagesArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "search_messages", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST users.profile.set */
  async setStatus(args: SetStatusArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "set_status", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST bookmarks.add */
  async addBookmark(args: AddBookmarkArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "add_bookmark", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET bookmarks.list */
  async listBookmarks(args: ListBookmarksArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_bookmarks", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST bookmarks.remove */
  async removeBookmark(args: RemoveBookmarkArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "remove_bookmark", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST reminders.add */
  async addReminder(args: AddReminderArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "add_reminder", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET reminders.list */
  async listReminders(args: ListRemindersArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_reminders", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST reminders.delete */
  async deleteReminder(args: DeleteReminderArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "delete_reminder", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET emoji.list */
  async listEmoji(args: ListEmojiArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_emoji", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST auth.test */
  async authTest(args: AuthTestArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "auth_test", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET team.info */
  async getTeamInfo(args: GetTeamInfoArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "get_team_info", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST usergroups.create */
  async createUsergroup(args: CreateUsergroupArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "create_usergroup", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET usergroups.list */
  async listUsergroups(args: ListUsergroupsArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "list_usergroups", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST usergroups.update */
  async updateUsergroup(args: UpdateUsergroupArgs): Promise<unknown> {
    return execute(SLACK_BINDING, "update_usergroup", args as unknown as Record<string, unknown>, this.credential);
  }
  /** ESCAPE HATCH — provide via new Slack(cred, { overrides }). */
  async uploadFile(args: Record<string, unknown>): Promise<unknown> {
    const fn = this.overrides["upload_file"];
    if (!fn) throw new Error("slack.upload_file is an escape-hatch action; pass an override");
    return fn(this.credential, args);
  }
}
