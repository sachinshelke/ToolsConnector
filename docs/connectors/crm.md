# CRM & Support

Connectors for customer relationship management and support platforms. 6 connectors, 106 actions.

---

### HubSpot

**Category:** CRM & Support | **Auth:** Private App Access Token | **Actions:** 8

Connect to HubSpot to manage contacts, deals, and CRM records.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_contacts | List contacts with optional filters | No |
| get_contact | Get a specific contact by ID | No |
| create_contact | Create a new contact | Yes |
| update_contact | Update an existing contact | No |
| list_deals | List deals in the pipeline | No |
| get_deal | Get a specific deal by ID | No |
| create_deal | Create a new deal | Yes |
| search_contacts | Search contacts by query | No |

**Quick start:**

```python
kit = ToolKit(["hubspot"], credentials={"hubspot": "pat-your-private-app-token"})
result = kit.execute("hubspot_list_contacts", {"limit": 20})
```

---

### Salesforce

**Category:** CRM & Support | **Auth:** OAuth2 Bearer Token | **Actions:** 8

Connect to Salesforce to query, create, and manage CRM records using SOQL and the REST API.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| query | Execute a SOQL query | No |
| get_record | Get a specific record by object type and ID | No |
| create_record | Create a new record | Yes |
| update_record | Update an existing record | No |
| delete_record | Delete a record by ID | Yes |
| describe_object | Get metadata for a Salesforce object | No |
| list_objects | List available Salesforce objects | No |
| search | Execute a SOSL search | No |

**Quick start:**

```python
kit = ToolKit(["salesforce"], credentials={"salesforce": {"access_token": "...", "instance_url": "https://yourorg.salesforce.com"}})
result = kit.execute("salesforce_query", {"soql": "SELECT Id, Name FROM Account LIMIT 10"})
```

---

### Zendesk

**Category:** CRM & Support | **Auth:** API Token (Basic Auth) | **Actions:** 8

Connect to Zendesk to manage support tickets, users, and perform searches.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_tickets | List tickets with optional filters | No |
| get_ticket | Get a specific ticket by ID | No |
| create_ticket | Create a new support ticket | Yes |
| update_ticket | Update an existing ticket | Yes |
| add_comment | Add a comment to a ticket | Yes |
| list_users | List Zendesk users | No |
| get_user | Get a specific user by ID | No |
| search | Search tickets, users, and organizations | No |

**Quick start:**

```python
kit = ToolKit(["zendesk"], credentials={"zendesk": {"email": "agent@company.com", "token": "your-api-token", "subdomain": "yourcompany"}})
result = kit.execute("zendesk_list_tickets", {"status": "open"})
```

---

### Freshdesk

**Category:** CRM & Support | **Auth:** API Key | **Actions:** 8

Connect to Freshdesk to manage support tickets and contacts.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_tickets | List tickets with optional filters | No |
| get_ticket | Get a specific ticket by ID | No |
| create_ticket | Create a new support ticket | Yes |
| update_ticket | Update an existing ticket | No |
| reply_to_ticket | Add a reply to a ticket | Yes |
| list_contacts | List contacts | No |
| get_contact | Get a specific contact by ID | No |
| search_tickets | Search tickets by query | No |

**Quick start:**

```python
kit = ToolKit(["freshdesk"], credentials={"freshdesk": {"api_key": "your-api-key", "domain": "yourcompany.freshdesk.com"}})
result = kit.execute("freshdesk_list_tickets", {"filter": "open"})
```

---

### Intercom

**Category:** CRM & Support | **Auth:** Access Token | **Actions:** 8

Connect to Intercom to manage contacts, conversations, and customer messaging.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_contacts | List contacts with optional filters | No |
| get_contact | Get a specific contact by ID | No |
| create_contact | Create a new contact | Yes |
| search_contacts | Search contacts by query | No |
| list_conversations | List conversations | No |
| get_conversation | Get a specific conversation by ID | No |
| reply_to_conversation | Reply to an existing conversation | Yes |
| create_message | Create a new outbound message | Yes |

**Quick start:**

```python
kit = ToolKit(["intercom"], credentials={"intercom": "your-access-token"})
result = kit.execute("intercom_list_contacts", {"per_page": 20})
```

---

### Odoo

**Category:** CRM & Support | **Auth:** API Key (url+db+username+api_key) | **Actions:** 11

Odoo (formerly OpenERP) — read & write any Odoo model (contacts, sales orders, invoices, inventory, HR, eCommerce, POS, Helpdesk, …) through its ORM over JSON-RPC. BYOK: instance url + db + username + API key.

Odoo is a full ERP — a single connector spanning CRM, Sales, Inventory, Accounting, HR, eCommerce, POS, Helpdesk, Manufacturing, Projects, and more. It is the first JSON-RPC connector in the catalog and exposes the generic ORM as a standardized primitive, so any model in any installed app is reachable through the same 11 actions.

**Install:** `pip install "toolsconnector[odoo]"`

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| get_version | Get the Odoo server version and metadata | No |
| search_read | Search records and read fields in a single call | No |
| search_count | Count records matching a domain | No |
| read | Read fields for records by ID | No |
| create | Create a new record | Yes |
| write | Update fields on existing records | Yes |
| unlink | Delete records by ID | Yes |
| name_search | Search records by display name | No |
| fields_get | Get field metadata for a model | No |
| read_group | Group and aggregate records | No |
| call_method | Call an arbitrary model method | Yes |

**Quick start:**

```python
kit = ToolKit(["odoo"], credentials={"odoo": {"url": "https://yourcompany.odoo.com", "db": "yourcompany", "username": "user@company.com", "api_key": "your-api-key"}})
result = kit.execute("odoo_search_read", {"model": "res.partner", "domain": [["is_company", "=", True]], "fields": ["name", "email"], "limit": 10})
```
