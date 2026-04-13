# Storage

Connectors for cloud file storage services. 2 connectors, 42 actions.

---

### Google Drive

**Category:** Storage | **Auth:** OAuth2 Bearer Token | **Actions:** 8

Connect to Google Drive to list, upload, download, search, and manage files and folders.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_files | List files and folders | No |
| get_file | Get metadata for a specific file | No |
| upload_file | Upload a file to Drive | No |
| download_file | Download a file from Drive | No |
| create_folder | Create a new folder | No |
| delete_file | Delete a file or folder | Yes |
| search_files | Search files with a query | No |
| share_file | Share a file with another user | Yes |

**Quick start:**

```python
kit = ToolKit(["gdrive"], credentials={"gdrive": "ya29.your-access-token"})
result = kit.execute("gdrive_list_files", {"page_size": 10})
```

**Extras required:** `pip install "toolsconnector[gdrive]"`

---

### S3

**Category:** Storage | **Auth:** AWS Access Key ID + Secret Access Key | **Actions:** 8

Connect to Amazon S3 to manage buckets and objects -- list, upload, download, copy, and delete.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_buckets | List all S3 buckets | No |
| create_bucket | Create a new S3 bucket | Yes |
| list_objects | List objects in a bucket | No |
| get_object | Download an object from a bucket | No |
| put_object | Upload an object to a bucket | Yes |
| delete_object | Delete an object from a bucket | Yes |
| head_object | Get metadata for an object without downloading | No |
| copy_object | Copy an object within or across buckets | No |

**Quick start:**

```python
kit = ToolKit(["s3"], credentials={"s3": {"aws_access_key_id": "AKIA...", "aws_secret_access_key": "..."}})
result = kit.execute("s3_list_buckets", {})
```

**Extras required:** `pip install "toolsconnector[s3]"`
