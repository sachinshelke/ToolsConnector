# DevOps & Cloud

Connectors for monitoring, deployment, CDN, and container services. 5 connectors, 40 actions.

---

### Datadog

**Category:** DevOps & Cloud | **Auth:** API Key + Application Key | **Actions:** 8

Connect to Datadog to manage monitors, query metrics, and work with events and dashboards.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_monitors | List all monitors | No |
| get_monitor | Get details of a specific monitor | No |
| create_monitor | Create a new monitor | Yes |
| mute_monitor | Mute a monitor | Yes |
| query_metrics | Query time-series metrics | No |
| list_events | List events with optional filters | No |
| create_event | Post a new event | Yes |
| list_dashboards | List all dashboards | No |

**Quick start:**

```python
kit = ToolKit(["datadog"], credentials={"datadog": {"api_key": "your-api-key", "app_key": "your-app-key"}})
result = kit.execute("datadog_list_monitors", {})
```

---

### PagerDuty

**Category:** DevOps & Cloud | **Auth:** API Token | **Actions:** 8

Connect to PagerDuty to manage incidents, services, and on-call schedules.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_incidents | List incidents with optional filters | No |
| get_incident | Get details of a specific incident | No |
| create_incident | Create a new incident | Yes |
| update_incident | Update an existing incident | Yes |
| acknowledge_incident | Acknowledge an incident | Yes |
| list_services | List all services | No |
| get_service | Get details of a specific service | No |
| list_oncalls | List current on-call entries | No |

**Quick start:**

```python
kit = ToolKit(["pagerduty"], credentials={"pagerduty": "your-api-token"})
result = kit.execute("pagerduty_list_incidents", {"statuses": ["triggered", "acknowledged"]})
```

---

### Vercel

**Category:** DevOps & Cloud | **Auth:** Bearer Token | **Actions:** 8

Connect to Vercel to manage deployments, projects, domains, and environment variables.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_deployments | List deployments with optional filters | No |
| get_deployment | Get details of a specific deployment | No |
| list_projects | List all projects | No |
| get_project | Get details of a specific project | No |
| list_domains | List domains for a project | No |
| add_domain | Add a domain to a project | Yes |
| list_env_vars | List environment variables for a project | No |
| create_env_var | Create an environment variable | Yes |

**Quick start:**

```python
kit = ToolKit(["vercel"], credentials={"vercel": "your-bearer-token"})
result = kit.execute("vercel_list_deployments", {"projectId": "prj_your-project-id", "limit": 5})
```

---

### Cloudflare

**Category:** DevOps & Cloud | **Auth:** API Token | **Actions:** 8

Connect to Cloudflare to manage DNS zones, DNS records, cache, and analytics.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_zones | List all DNS zones | No |
| get_zone | Get details of a specific zone | No |
| list_dns_records | List DNS records for a zone | No |
| create_dns_record | Create a new DNS record | Yes |
| update_dns_record | Update an existing DNS record | Yes |
| delete_dns_record | Delete a DNS record | Yes |
| purge_cache | Purge cached content for a zone | Yes |
| get_analytics | Get analytics data for a zone | No |

**Quick start:**

```python
kit = ToolKit(["cloudflare"], credentials={"cloudflare": "your-api-token"})
result = kit.execute("cloudflare_list_zones", {})
```

---

### Docker Hub

**Category:** DevOps & Cloud | **Auth:** Access Token | **Actions:** 8

Connect to Docker Hub to search repositories, list tags, and manage organizations.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| search_repos | Search public repositories | No |
| get_repo | Get details of a specific repository | No |
| list_repos | List repositories for a user or organization | No |
| list_tags | List tags for a repository | No |
| get_tag | Get details of a specific tag | No |
| get_user | Get details of a user | No |
| list_orgs | List organizations for the user | No |
| get_org | Get details of a specific organization | No |

**Quick start:**

```python
kit = ToolKit(["dockerhub"], credentials={"dockerhub": "your-access-token"})
result = kit.execute("dockerhub_search_repos", {"query": "python"})
```
