# AI/ML

Connectors for AI model providers and vector databases. 8 connectors, 171 actions.

---

### OpenAI

**Category:** AI/ML | **Auth:** API Key | **Actions:** 26

Connect to the OpenAI API to generate completions, embeddings, images, transcriptions, and manage assistants.

**Actions (26 total — sample):**

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

**Category:** AI/ML | **Auth:** API Key | **Actions:** 14

Connect to the Anthropic API to generate messages, count tokens, and list available models.

**Actions (14 total — sample):**

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

**Category:** AI/ML | **Auth:** API Key | **Actions:** 15

Connect to Pinecone to manage vector indexes, upsert vectors, query for nearest neighbors, and inspect index statistics.

**Actions (15 total — sample):**

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

---

### Hugging Face

**Category:** AI/ML | **Auth:** API Key | **Actions:** 30 | **Verification:** ✅ Tier 1 (Live verified — 24/30)

Connect to Hugging Face to run hosted model inference across the full task set (text generation, chat completion, embeddings, classification, NER, vision, and audio) and to search models, datasets, and Spaces on the Hub.

**Actions (30 total — sample):**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| audio_classification | Classify audio into labels | No |
| automatic_speech_recognition | Transcribe speech audio to text | No |
| chat_completion | Create a chat completion via the OpenAI-compatible router | No |
| feature_extraction | Extract embedding vectors from text | No |
| fill_mask | Fill a masked token in text with a hosted model | No |
| get_dataset | Get metadata for a dataset on the Hub | No |
| get_model | Get metadata for a model on the Hub | No |
| get_space | Get metadata for a Space on the Hub | No |
| … | +19 more actions — see the connector README | |

**Quick start:**

```python
kit = ToolKit(["huggingface"], credentials={"huggingface": "hf_your-token"})
result = kit.execute("huggingface_zero_shot_classification", {"model": "facebook/bart-large-mnli", "inputs": "I need a refund", "candidate_labels": ["billing", "tech support"]})
```

---
### Google Gemini

**Category:** AI/ML | **Auth:** API Key | **Actions:** 19

Connect to Google Gemini for generating content with Gemini models, counting tokens, creating embeddings, managing uploaded files, context caches, and tuned models.

**Actions (19 total — sample):**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| batch_embed_contents | Create embeddings for multiple texts | No |
| count_tokens | Count tokens for a prompt | No |
| create_cache | Create a context cache | No |
| create_tuned_model | Create a tuned model | Yes |
| delete_cache | Delete a context cache | Yes |
| delete_file | Delete an uploaded file | Yes |
| delete_tuned_model | Delete a tuned model | Yes |
| embed_content | Create an embedding for a single text | No |
| … | +11 more actions — see the connector README | |

**Quick start:**

```python
kit = ToolKit(["gemini"], credentials={"gemini": "your-api-key"})
result = kit.execute("gemini_generate_content", {"model": "gemini-2.0-flash", "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]})
```

---
### Cohere

**Category:** AI/ML | **Auth:** API Key | **Actions:** 22

Connect to Cohere for chat completions, text embeddings, document reranking, text classification, tokenization, batch embed jobs, dataset management, and model fine-tuning.

**Actions (22 total — sample):**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| cancel_embed_job | Cancel a running batch embed job | Yes |
| chat | Generate a chat response | No |
| check_api_key | Check whether the API key is valid | No |
| classify | Classify text into labelled categories | No |
| create_dataset | Create a dataset from an uploaded file | No |
| create_embed_job | Create a batch embed job | No |
| create_finetuned_model | Create a fine-tuned model | No |
| delete_dataset | Delete a dataset | Yes |
| … | +14 more actions — see the connector README | |

**Quick start:**

```python
kit = ToolKit(["cohere"], credentials={"cohere": "your-api-key"})
result = kit.execute("cohere_rerank", {"model": "rerank-v3.5", "query": "best laptop", "documents": ["MacBook Pro", "garden hose"]})
```

---
### Mistral

**Category:** AI/ML | **Auth:** API Key | **Actions:** 30

Connect to Mistral AI for chat, embeddings, FIM and agent completions, content moderation and classification, OCR, plus file, fine-tuning-job, batch-job, and model management.

**Actions (30 total — sample):**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| agents_completion | Create an agent completion | No |
| archive_model | Archive a fine-tuned model | No |
| cancel_batch_job | Cancel a batch job | Yes |
| cancel_finetuning_job | Cancel a fine-tuning job | Yes |
| chat_completion | Create a chat completion | No |
| chat_moderations | Run content moderation on a conversation | No |
| classifications | Classify text with a classifier model | No |
| create_batch_job | Create a batch job | No |
| … | +22 more actions — see the connector README | |

**Quick start:**

```python
kit = ToolKit(["mistral"], credentials={"mistral": "your-api-key"})
result = kit.execute("mistral_chat_completion", {"model": "mistral-large-latest", "messages": [{"role": "user", "content": "Hello"}]})
```

---
### Groq

**Category:** AI/ML | **Auth:** API Key | **Actions:** 15

Connect to Groq for ultra-low-latency chat completions on open models (Llama, Mixtral), model discovery, Whisper audio transcription and translation, PlayAI text-to-speech, file management, and the asynchronous Batch API.

**Actions (15 total — sample):**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| cancel_batch | Cancel a batch job | Yes |
| chat_completion | Create a chat completion | No |
| create_batch | Create a batch job | No |
| create_speech | Generate speech audio from text | No |
| delete_file | Delete an uploaded file | Yes |
| get_batch | Get a batch job by ID | No |
| get_file | Get file metadata by ID | No |
| get_file_content | Get file content by ID | No |
| … | +7 more actions — see the connector README | |

**Quick start:**

```python
kit = ToolKit(["groq"], credentials={"groq": "your-api-key"})
result = kit.execute("groq_chat_completion", {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Hello"}]})
```
