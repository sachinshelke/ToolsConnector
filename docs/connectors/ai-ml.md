# AI/ML

Connectors for AI model providers and vector databases. 3 connectors, 19 actions.

---

### OpenAI

**Category:** AI/ML | **Auth:** API Key | **Actions:** 8

Connect to the OpenAI API to generate completions, embeddings, images, transcriptions, and manage assistants.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| chat_completion | Generate a chat completion | No |
| list_models | List available models | No |
| create_embedding | Create an embedding vector | No |
| create_image | Generate an image from a prompt | No |
| transcribe_audio | Transcribe audio to text | No |
| list_assistants | List assistants | No |
| create_assistant | Create a new assistant | No |
| list_files | List uploaded files | No |

**Quick start:**

```python
kit = ToolKit(["openai"], credentials={"openai": "sk-your-api-key"})
result = kit.execute("openai_chat_completion", {"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]})
```

---

### Anthropic

**Category:** AI/ML | **Auth:** API Key | **Actions:** 3

Connect to the Anthropic API to generate messages, count tokens, and list available models.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| create_message | Create a message (chat completion) | No |
| count_tokens | Count tokens for a message | No |
| list_models | List available models | No |

**Quick start:**

```python
kit = ToolKit(["anthropic"], credentials={"anthropic": "sk-ant-your-api-key"})
result = kit.execute("anthropic_create_message", {"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 256})
```

---

### Pinecone

**Category:** AI/ML | **Auth:** API Key | **Actions:** 8

Connect to Pinecone to manage vector indexes, upsert vectors, query for nearest neighbors, and inspect index statistics.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| upsert | Upsert vectors into an index | No |
| query | Query an index for nearest neighbors | No |
| delete | Delete vectors from an index | Yes |
| describe_index_stats | Get statistics for an index | No |
| fetch | Fetch vectors by ID | No |
| update | Update vector metadata | No |
| list_vectors | List vector IDs in an index | No |
| list_indexes | List all indexes | No |

**Quick start:**

```python
kit = ToolKit(["pinecone"], credentials={"pinecone": {"api_key": "your-api-key", "environment": "us-east1-gcp"}})
result = kit.execute("pinecone_query", {"index": "my-index", "vector": [0.1, 0.2, 0.3], "top_k": 5})
```
