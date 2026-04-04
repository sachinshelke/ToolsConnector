# Database

Connectors for database and data platform services. 5 connectors, 39 actions.

---

### Supabase

**Category:** Database | **Auth:** API Key (anon or service_role) | **Actions:** 7

Connect to Supabase to query, insert, update, and delete records in your PostgreSQL tables through the Supabase REST API.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| query_table | Query records from a table with filters | No |
| get_record | Get a single record by ID | No |
| insert_record | Insert a new record into a table | No |
| update_record | Update an existing record | No |
| upsert_record | Insert or update a record based on conflict | No |
| delete_record | Delete a record by ID | Yes |
| list_tables | List all tables in the database | No |

**Quick start:**

```python
kit = ToolKit(["supabase"], credentials={"supabase": {"url": "https://your-project.supabase.co", "key": "your-anon-key"}})
result = kit.execute("supabase_query_table", {"table": "users", "select": "*", "limit": 10})
```

---

### MongoDB

**Category:** Database | **Auth:** Connection String or API Key | **Actions:** 8

Connect to MongoDB to find, insert, update, and aggregate documents using the MongoDB Data API.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| find | Find documents matching a filter | No |
| find_one | Find a single document matching a filter | No |
| insert_one | Insert a single document | No |
| insert_many | Insert multiple documents | No |
| update_one | Update a single document matching a filter | No |
| delete_one | Delete a single document matching a filter | Yes |
| aggregate | Run an aggregation pipeline | No |
| count | Count documents matching a filter | No |

**Quick start:**

```python
kit = ToolKit(["mongodb"], credentials={"mongodb": {"api_key": "your-data-api-key", "cluster": "your-cluster", "database": "mydb"}})
result = kit.execute("mongodb_find", {"collection": "users", "filter": {"active": True}})
```

---

### Airtable

**Category:** Database | **Auth:** Personal Access Token | **Actions:** 8

Connect to Airtable to manage bases, tables, and records.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_bases | List all accessible bases | No |
| get_base_schema | Get the schema of a base | No |
| list_records | List records in a table | No |
| get_record | Get a single record by ID | No |
| create_record | Create a new record in a table | No |
| batch_create | Create multiple records at once | No |
| update_record | Update an existing record | No |
| delete_record | Delete a record by ID | Yes |

**Quick start:**

```python
kit = ToolKit(["airtable"], credentials={"airtable": "pat_your-personal-access-token"})
result = kit.execute("airtable_list_records", {"base_id": "appXXXXXX", "table_name": "Tasks"})
```

---

### Firestore

**Category:** Database | **Auth:** Service Account JSON or Bearer Token | **Actions:** 8

Connect to Google Cloud Firestore to manage documents and collections.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| get_document | Get a document by path | No |
| list_documents | List documents in a collection | No |
| list_collections | List collections in the database | No |
| create_document | Create a new document | No |
| update_document | Update an existing document | No |
| delete_document | Delete a document by path | Yes |
| query | Query documents with structured filters | No |
| batch_write | Execute multiple write operations atomically | No |

**Quick start:**

```python
kit = ToolKit(["firestore"], credentials={"firestore": {"project_id": "my-project", "token": "your-access-token"}})
result = kit.execute("firestore_list_documents", {"collection": "users"})
```

---

### Redis

**Category:** Database | **Auth:** Connection URL or API Token | **Actions:** 8

Connect to Redis to get, set, delete keys, and work with hashes and lists.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| get | Get the value of a key | No |
| set | Set a key to a value | No |
| delete | Delete a key | Yes |
| keys | List keys matching a pattern | No |
| hget | Get a field from a hash | No |
| hset | Set a field in a hash | No |
| lpush | Push a value onto a list | No |
| lrange | Get a range of values from a list | No |

**Quick start:**

```python
kit = ToolKit(["redis"], credentials={"redis": "redis://localhost:6379"})
result = kit.execute("redis_get", {"key": "session:user123"})
```
