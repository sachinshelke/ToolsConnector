# Communication

Connectors for email, messaging, and SMS services. 7 connectors, 56 actions.

---

### Gmail

**Category:** Communication | **Auth:** OAuth2 Bearer Token | **Actions:** 8

Connect to Gmail to read, send, search, and manage emails and labels.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_emails | List emails matching a query | No |
| get_email | Get a single email by ID | No |
| send_email | Send an email | Yes |
| search_emails | Search emails with a query string | No |
| list_labels | List all Gmail labels | No |
| create_draft | Create an email draft | No |
| delete_email | Delete an email by ID | Yes |
| modify_labels | Add or remove labels on an email | No |

**Quick start:**

```python
kit = ToolKit(["gmail"], credentials={"gmail": "ya29.your-access-token"})
result = kit.execute("gmail_list_emails", {"query": "is:unread", "max_results": 10})
```

**Extras required:** `pip install "toolsconnector[gmail]"`

---

### Slack

**Category:** Communication | **Auth:** Bot Token (xoxb-) | **Actions:** 8

Connect to Slack to send messages, list channels, upload files, and manage reactions.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| send_message | Send a message to a channel or thread | Yes |
| list_channels | List channels in the workspace | No |
| get_channel | Get details of a specific channel | No |
| list_messages | List messages in a channel | No |
| upload_file | Upload a file to a channel | Yes |
| add_reaction | Add an emoji reaction to a message | No |
| list_users | List users in the workspace | No |
| get_user | Get details of a specific user | No |

**Quick start:**

```python
kit = ToolKit(["slack"], credentials={"slack": "xoxb-your-bot-token"})
kit.execute("slack_send_message", {"channel": "#general", "text": "Hello from ToolsConnector"})
```

---

### Discord

**Category:** Communication | **Auth:** Bot Token | **Actions:** 8

Connect to Discord to send messages, manage channels, and interact with guild members.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| send_message | Send a message to a channel | Yes |
| list_channels | List channels in a guild | No |
| get_channel | Get details of a specific channel | No |
| list_messages | List messages in a channel | No |
| create_channel | Create a new channel in a guild | Yes |
| add_reaction | Add a reaction to a message | No |
| list_guild_members | List members of a guild | No |
| get_user | Get details of a specific user | No |

**Quick start:**

```python
kit = ToolKit(["discord"], credentials={"discord": "your-bot-token"})
kit.execute("discord_send_message", {"channel_id": "123456", "content": "Hello"})
```

---

### Outlook

**Category:** Communication | **Auth:** OAuth2 Bearer Token (Microsoft Graph) | **Actions:** 8

Connect to Outlook to read, send, and manage emails through the Microsoft Graph API.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_messages | List messages in the mailbox | No |
| get_message | Get a single message by ID | No |
| send_message | Send an email | Yes |
| list_folders | List mail folders | No |
| search_messages | Search messages with a query | No |
| delete_message | Delete a message by ID | Yes |
| create_draft | Create an email draft | No |
| reply_to_message | Reply to a specific message | Yes |

**Quick start:**

```python
kit = ToolKit(["outlook"], credentials={"outlook": "your-graph-access-token"})
result = kit.execute("outlook_list_messages", {"top": 10})
```

---

### Teams

**Category:** Communication | **Auth:** OAuth2 Bearer Token (Microsoft Graph) | **Actions:** 8

Connect to Microsoft Teams to send messages, manage channels, and list team members.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_teams | List teams the user belongs to | No |
| get_team | Get details of a specific team | No |
| list_channels | List channels in a team | No |
| send_message | Send a message to a channel | Yes |
| list_messages | List messages in a channel | No |
| list_members | List members of a team | No |
| create_channel | Create a new channel in a team | No |
| get_channel | Get details of a specific channel | No |

**Quick start:**

```python
kit = ToolKit(["teams"], credentials={"teams": "your-graph-access-token"})
result = kit.execute("teams_list_teams", {})
```

---

### Twilio

**Category:** Communication | **Auth:** Account SID + Auth Token | **Actions:** 8

Connect to Twilio to send SMS messages, make calls, and manage phone numbers.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| send_sms | Send an SMS message | Yes |
| list_messages | List sent and received messages | No |
| get_message | Get details of a specific message | No |
| list_calls | List call records | No |
| make_call | Initiate a phone call | Yes |
| get_call | Get details of a specific call | No |
| list_phone_numbers | List phone numbers on the account | No |
| get_account | Get account details | No |

**Quick start:**

```python
kit = ToolKit(["twilio"], credentials={"twilio": {"account_sid": "AC...", "auth_token": "..."}})
kit.execute("twilio_send_sms", {"to": "+1234567890", "from_": "+0987654321", "body": "Hello"})
```

---

### Telegram

**Category:** Communication | **Auth:** Bot Token | **Actions:** 8

Connect to Telegram to send messages, photos, and documents through the Bot API.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| send_message | Send a text message to a chat | No |
| get_updates | Get incoming updates (messages, etc.) | No |
| get_chat | Get details of a specific chat | No |
| get_chat_members_count | Get the number of members in a chat | No |
| send_photo | Send a photo to a chat | No |
| send_document | Send a document to a chat | No |
| edit_message | Edit a previously sent message | No |
| delete_message | Delete a message | Yes |

**Quick start:**

```python
kit = ToolKit(["telegram"], credentials={"telegram": "your-bot-token"})
kit.execute("telegram_send_message", {"chat_id": "123456", "text": "Hello from ToolsConnector"})
```
