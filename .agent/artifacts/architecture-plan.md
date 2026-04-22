# ToolsConnector — Foundation-Grade Architecture Plan

## Context & CTO-Level Review

### Why This Plan Exists
The brainstorm (`plan/brainstorm.md`) captured a brilliant vision and settled core philosophical debates. But it has gaps that would prevent ToolsConnector from becoming a true industry primitive:

1. **The brainstorm thinks in terms of Gmail/Slack** — but 1000+ tools span REST, GraphQL, SOAP, gRPC, WebSocket, SSE. The architecture must handle ALL communication protocols, not just REST.
2. **"Language-agnostic spec" is mentioned but never defined** — this is THE most important piece for multi-language SDKs and it's completely absent.
3. **Auth is oversimplified** — the brainstorm covers OAuth2 and API keys, but the real world has mTLS, SAML, OIDC, AWS SigV4, HMAC signing, device code flow, PKCE, and custom auth. A primitive must handle ALL of them.
4. **Pagination assumes cursor-based** — but real APIs use offset, keyset, page-number, link-header, and streaming. Each needs first-class support.
5. **No protocol abstraction layer** — the brainstorm jumps from BaseConnector directly to HTTP calls. A primitive needs a protocol adapter layer between business logic and transport.
6. **Security model is thin** — BYOK is correct philosophy, but for Foundation-grade we need threat model, supply chain security, signed releases, SBOM, CVE process.
7. **No formal spec = no multi-language** — without a Connector Definition Specification, TypeScript/Go/Java SDKs will drift.

### What the Brainstorm Got Right (Don't Change)
- "Primitive, not platform" positioning
- Dual-use (traditional + AI) — this is the killer insight
- Kafka open-source model (Apache 2.0)
- BYOK auth philosophy
- Full capability, not dumbed-down interfaces
- Health Agent concept (genuine differentiator)
- Package-with-extras distribution
- Separate `toolsconnector-mcp` package

### What Needs Revision
- Architecture needs a **Protocol Adapter Layer** (not just raw httpx)
- Auth needs to be a **pluggable provider system** (not just an enum)
- Pagination needs **strategy pattern** (not just PaginatedList)
- Need a formal **Connector Definition Specification (CDS)** for multi-language
- Need **conformance test framework** for quality at scale
- Need **security policy** and **governance RFC process** from day one

---

## Part 1: The Connector Definition Specification (CDS)

### Why Spec-First Matters

For every Foundation-grade multi-language project (OpenTelemetry, CloudEvents, gRPC, GraphQL), the **specification IS the primitive**. Language implementations are SDKs.

ToolsConnector's spec defines: *What does it mean to be a "connector"? What contracts must every connector fulfill?*

### Approach: Spec-Embedded Implementation

We don't write a 200-page spec document before coding. Instead:
- Python is the **reference implementation** — the spec is embedded in the code via `@action` decorators, Pydantic models, and type hints
- The runtime **auto-extracts** the spec as JSON Schema (via `Connector.get_spec() -> ConnectorSpec`)
- When TypeScript/Go/Java SDKs begin, we **formalize** the spec into standalone `SPEC.md` + JSON Schema files
- Conformance tests are written against the spec, runnable from any language

This is how gRPC did it — protobuf was designed alongside Go/C++ implementations, not separately.

### ConnectorSpec Format (auto-generated from Python, later standalone)

```yaml
# gmail.connector.yaml — auto-generated from Python, later hand-authored for other languages
spec_version: "1.0"
connector:
  name: gmail
  display_name: Gmail
  category: communication
  description: "Connect to Gmail to read, send, and manage emails."
  version: "1.0.0"

  protocol: rest                    # rest | graphql | soap | grpc | websocket | custom
  base_url: "https://gmail.googleapis.com"

  auth:
    supported:
      - type: oauth2
        config:
          auth_url: "https://accounts.google.com/o/oauth2/auth"
          token_url: "https://oauth2.googleapis.com/token"
          scopes:
            read: ["https://www.googleapis.com/auth/gmail.readonly"]
            send: ["https://www.googleapis.com/auth/gmail.send"]
            full: ["https://www.googleapis.com/auth/gmail.modify"]
      - type: service_account
        config:
          credential_format: json_keyfile

  rate_limits:
    default:
      rate: 250              # requests per period
      period: 60              # seconds
      burst: 50
    per_action:
      send_email:
        rate: 100
        period: 86400         # daily limit

  actions:
    list_emails:
      description: "List emails matching a query"
      requires_scope: read
      dangerous: false
      pagination:
        strategy: token       # token | offset | cursor | keyset | link_header | none
        token_field: nextPageToken
        items_field: messages
      input_schema:           # JSON Schema
        type: object
        properties:
          query:
            type: string
            default: "is:unread"
            description: "Gmail search query syntax"
          limit:
            type: integer
            default: 10
            minimum: 1
            maximum: 500
          labels:
            type: array
            items: { type: string }
            nullable: true
      output_schema:
        $ref: "#/types/PaginatedList_Email"

    send_email:
      description: "Send an email to a recipient"
      requires_scope: send
      dangerous: true          # flagged for human-in-the-loop
      idempotency: optional    # none | required | optional
      input_schema:
        type: object
        required: [to, subject, body]
        properties:
          to: { type: string, format: email }
          subject: { type: string }
          body: { type: string }
          cc:
            type: array
            items: { type: string, format: email }
            nullable: true
          attachments:
            type: array
            items: { $ref: "#/types/FileRef" }
            nullable: true
      output_schema:
        $ref: "#/types/MessageId"

  events: []                   # v2: webhook event types

  types:
    Email:
      type: object
      properties:
        id: { type: string }
        thread_id: { type: string }
        subject: { type: string }
        from_address: { type: string }
        to: { type: array, items: { type: string } }
        date: { type: string, format: date-time }
        snippet: { type: string }
        labels: { type: array, items: { type: string } }
        has_attachments: { type: boolean }
    MessageId:
      type: object
      properties:
        id: { type: string }
```

### What This Enables
- **Any language SDK** can implement a connector that matches this spec
- **Conformance tests** verify behavior against the spec
- **Code generators** can scaffold connector stubs from spec files
- **Documentation** is auto-generated from the spec
- **MCP/OpenAI/Anthropic schemas** are derived from the spec
- **Health Agent** validates connectors against their spec

---

## Part 2: Layer Architecture (Revised)

### The Problem With the Brainstorm Architecture

The brainstorm has: `Connector → raw httpx calls`. This breaks for:
- GraphQL APIs (Shopify, Linear, GitHub) — need query building
- SOAP APIs (SAP, legacy banking) — need XML envelope construction
- gRPC APIs (Google Cloud internal) — need protobuf serialization
- WebSocket APIs (Slack real-time, Discord) — need persistent connections
- Database connectors (PostgreSQL, MongoDB) — need connection pools + SQL

### The Revised Layer Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                     SERVE LAYER (optional)                       │
│  MCP Server │ REST API │ CLI │ Schema Gen │ Framework Adapters   │
├─────────────────────────────────────────────────────────────────┤
│                     CONNECTOR LAYER                              │
│  Gmail, Slack, Salesforce, SAP, PostgreSQL, Kafka, ...          │
│  Business logic + tool-specific types + action implementations  │
├─────────────────────────────────────────────────────────────────┤
│                     RUNTIME LAYER                                │
│  Middleware Pipeline │ Pagination Engine │ Error Normalization   │
│  Serialization │ Validation │ Sync/Async Bridge                 │
├─────────────────────────────────────────────────────────────────┤
│                     PROTOCOL ADAPTER LAYER      ← NEW           │
│  RESTAdapter │ GraphQLAdapter │ SOAPAdapter │ GRPCAdapter       │
│  WebSocketAdapter │ DatabaseAdapter │ MessageQueueAdapter       │
├─────────────────────────────────────────────────────────────────┤
│                     AUTH PROVIDER LAYER          ← EXPANDED     │
│  APIKeyAuth │ OAuth2Auth │ OAuth2PKCEAuth │ OIDCAuth           │
│  SAMLAuth │ mTLSAuth │ HMACAuth │ SigV4Auth │ CustomAuth      │
├─────────────────────────────────────────────────────────────────┤
│                     TRANSPORT LAYER                              │
│  HTTP (httpx) │ WebSocket (websockets) │ TCP │ gRPC (grpcio)   │
├─────────────────────────────────────────────────────────────────┤
│                     RESILIENCE LAYER                             │
│  Retry │ Rate Limiter │ Circuit Breaker │ Timeout │ Bulkhead   │
├─────────────────────────────────────────────────────────────────┤
│                     KEYSTORE LAYER                               │
│  InMemory │ Env │ LocalFile │ Vault │ AWS SM │ Custom          │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Layering Matters

A connector author writing a Gmail connector doesn't care about HTTP. They say:
```python
response = await self.rest.get("/gmail/v1/users/me/messages", params={...})
```

A connector author writing a Shopify connector says:
```python
response = await self.graphql.query("{ products(first: 10) { edges { node { title } } } }")
```

A connector author writing an SAP connector says:
```python
response = await self.soap.call("GetCustomerList", params={...})
```

The protocol adapter handles the format differences. The connector focuses on business logic.

---

## Part 3: Core Primitive Design (Detailed)

### 3.1 Module Structure

```
toolsconnector/
├── __init__.py                    # Public API: Connector, action, Auth, PaginatedList
│
├── spec/                          # Specification types (NO implementation logic)
│   ├── __init__.py
│   ├── connector.py               # ConnectorSpec — the interface contract
│   ├── action.py                  # ActionSpec — action definitions
│   ├── auth.py                    # AuthSpec — auth configuration
│   ├── types.py                   # TypeSpec — type definitions
│   ├── pagination.py              # PaginationSpec — pagination patterns
│   ├── errors.py                  # ErrorSpec — error codes/categories
│   └── version.py                 # Spec version constant
│
├── runtime/                       # The execution engine
│   ├── __init__.py
│   ├── base.py                    # BaseConnector — abstract base class
│   ├── action.py                  # @action decorator + ActionMeta
│   ├── context.py                 # ActionContext — execution context
│   ├── registry.py                # ConnectorRegistry — discovery
│   ├── _sync.py                   # run_sync() utility
│   │
│   ├── auth/                      # Auth provider system
│   │   ├── __init__.py
│   │   ├── base.py                # AuthProvider protocol
│   │   ├── manager.py             # AuthManager — lifecycle orchestration
│   │   ├── api_key.py             # API key auth
│   │   ├── bearer.py              # Bearer token auth
│   │   ├── oauth2.py              # OAuth 2.0 (authorization code)
│   │   ├── oauth2_pkce.py         # OAuth 2.0 + PKCE
│   │   ├── oidc.py                # OpenID Connect
│   │   ├── basic.py               # Basic auth
│   │   ├── hmac.py                # HMAC request signing
│   │   ├── service_account.py     # Google/Firebase service accounts
│   │   └── custom.py              # Custom auth provider base
│   │
│   ├── protocol/                  # Protocol adapter layer
│   │   ├── __init__.py
│   │   ├── base.py                # ProtocolAdapter protocol
│   │   ├── rest.py                # REST adapter (JSON/XML over HTTP)
│   │   ├── graphql.py             # GraphQL adapter (queries/mutations)
│   │   ├── soap.py                # SOAP adapter (XML envelope)
│   │   └── custom.py              # Custom protocol base
│   │
│   ├── middleware/                 # Middleware pipeline
│   │   ├── __init__.py
│   │   ├── base.py                # Middleware protocol
│   │   ├── auth.py                # AuthMiddleware
│   │   ├── retry.py               # RetryMiddleware
│   │   ├── rate_limit.py          # RateLimitMiddleware
│   │   ├── logging.py             # LoggingMiddleware
│   │   ├── idempotency.py         # IdempotencyMiddleware
│   │   └── circuit_breaker.py     # CircuitBreakerMiddleware
│   │
│   ├── pagination/                # Pagination strategies
│   │   ├── __init__.py
│   │   ├── base.py                # PaginationStrategy protocol
│   │   ├── cursor.py              # Cursor/token-based pagination
│   │   ├── offset.py              # Offset-limit pagination
│   │   ├── keyset.py              # Keyset pagination
│   │   ├── page_number.py         # Page number pagination
│   │   ├── link_header.py         # RFC 5988 link header
│   │   └── none.py                # No pagination (single response)
│   │
│   ├── serialization/             # Data format handling
│   │   ├── __init__.py
│   │   ├── base.py                # Serializer protocol
│   │   ├── json.py                # JSON serialization
│   │   ├── xml.py                 # XML serialization
│   │   └── multipart.py           # Multipart/form-data
│   │
│   └── transport/                 # Transport layer
│       ├── __init__.py
│       ├── base.py                # Transport protocol
│       └── http.py                # HTTP transport (httpx)
│
├── types/                         # Shared framework types
│   ├── __init__.py
│   ├── paginated.py               # PaginatedList[T]
│   ├── file.py                    # FileRef + StorageBackend
│   ├── credentials.py             # CredentialSet, OAuthConfig
│   └── common.py                  # DateTime, URL, Email wrappers
│
├── errors/                        # Error hierarchy
│   ├── __init__.py
│   ├── base.py                    # ToolsConnectorError base
│   ├── auth.py                    # AuthError subtree
│   ├── api.py                     # APIError subtree
│   ├── transport.py               # TransportError subtree
│   ├── config.py                  # ConfigError subtree
│   └── codes.py                   # Error code registry
│
├── keystore/                      # Credential storage
│   ├── __init__.py
│   ├── base.py                    # KeyStore protocol
│   ├── memory.py                  # InMemoryKeyStore
│   ├── env.py                     # EnvironmentKeyStore
│   └── local.py                   # LocalFileKeyStore (Fernet)
│
├── connectors/                    # Connector implementations
│   ├── __init__.py
│   └── gmail/                     # (example — each tool is a subpackage)
│       ├── __init__.py
│       ├── connector.py
│       └── types.py
│
├── serve/                         # Exposure layer
│   ├── __init__.py
│   ├── mcp.py                    # MCP server generation
│   ├── schema.py                 # Multi-framework schema generation
│   ├── rest.py                   # REST API exposure
│   └── cli.py                    # tc CLI
│
├── codegen/                       # Code generation for multi-language
│   ├── __init__.py
│   ├── spec_extractor.py          # Extract ConnectorSpec from Python class
│   ├── typescript.py              # Generate TypeScript stubs
│   ├── openapi.py                 # Generate OpenAPI from spec
│   └── docs.py                    # Generate documentation
│
└── health/                        # Connector health agent
    ├── __init__.py
    ├── watcher.py
    ├── analyzer.py
    └── reporter.py

# --- Separate package ---
toolsconnector-mcp/
├── pyproject.toml
└── toolsconnector_mcp/
    ├── __init__.py
    ├── server.py                  # Enhanced multi-tool MCP server
    ├── selection.py               # Smart tool selection
    ├── registry.py                # Tool discovery
    └── multi_tenant.py            # Multi-tenant MCP serving
```

### 3.2 The spec/ Module — Pure Specification Types

These are **Pydantic models that define the contract**. No implementation logic. Any language SDK must produce/consume these shapes.

```python
# toolsconnector/spec/connector.py

class ConnectorSpec(BaseModel):
    """The complete specification of a connector.
    This is the language-agnostic interface contract.
    Auto-extracted from Python connectors via get_spec().
    Can also be authored standalone in YAML/JSON."""

    spec_version: str = "1.0"
    name: str
    display_name: str
    category: ConnectorCategory
    description: str
    version: str

    protocol: ProtocolType            # rest, graphql, soap, grpc, websocket, custom
    base_url: str | None = None

    auth: AuthSpec
    rate_limits: RateLimitSpec
    actions: dict[str, ActionSpec]
    events: list[EventSpec] = []      # v2: webhook/streaming events
    types: dict[str, dict]            # JSON Schema type definitions

class ConnectorCategory(str, Enum):
    COMMUNICATION = "communication"        # Gmail, Slack, Teams, Discord
    PROJECT_MANAGEMENT = "project_management"  # Jira, Asana, Linear
    CRM = "crm"                            # Salesforce, HubSpot
    CODE_PLATFORM = "code_platform"        # GitHub, GitLab
    STORAGE = "storage"                    # S3, GDrive, Dropbox
    KNOWLEDGE = "knowledge"                # Notion, Confluence
    DATABASE = "database"                  # PostgreSQL, MongoDB
    ANALYTICS = "analytics"                # GA4, Mixpanel, BigQuery
    FINANCE = "finance"                    # Stripe, QuickBooks
    MARKETING = "marketing"                # Mailchimp, HubSpot Marketing
    HR = "hr"                              # Workday, BambooHR
    ECOMMERCE = "ecommerce"                # Shopify, WooCommerce
    DEVOPS = "devops"                      # AWS, GCP, K8s
    SOCIAL = "social"                      # Twitter, LinkedIn
    MESSAGE_QUEUE = "message_queue"        # Kafka, RabbitMQ, SQS
    CUSTOM = "custom"

class ProtocolType(str, Enum):
    REST = "rest"
    GRAPHQL = "graphql"
    SOAP = "soap"
    GRPC = "grpc"
    WEBSOCKET = "websocket"
    DATABASE = "database"
    MESSAGE_QUEUE = "message_queue"
    CUSTOM = "custom"
```

### 3.3 Protocol Adapter Layer

This is the critical new layer. Each protocol adapter normalizes a communication pattern into a consistent interface.

```python
# toolsconnector/runtime/protocol/base.py

class ProtocolAdapter(Protocol):
    """Abstracts communication protocol differences."""

    async def request(
        self,
        operation: str,          # Action name or endpoint
        *,
        method: str | None = None,
        params: dict | None = None,
        body: Any = None,
        headers: dict | None = None,
    ) -> ProtocolResponse: ...

    async def close(self) -> None: ...

class ProtocolResponse(BaseModel):
    """Normalized response from any protocol."""
    status: int | None = None    # HTTP status (None for non-HTTP)
    data: Any                     # Parsed response body
    raw: bytes | None = None     # Raw response bytes
    headers: dict[str, str] = {}
    metadata: dict[str, Any] = {}  # Protocol-specific metadata
```

**REST Adapter** — handles JSON/XML over HTTP:
```python
class RESTAdapter(ProtocolAdapter):
    async def request(self, operation, *, method="GET", params=None, body=None, **kw):
        response = await self._http.request(method, operation, params=params, json=body)
        return ProtocolResponse(status=response.status_code, data=response.json(), ...)
```

**GraphQL Adapter** — handles query/mutation building:
```python
class GraphQLAdapter(ProtocolAdapter):
    async def request(self, operation, *, body=None, **kw):
        # operation = query string, body = variables
        payload = {"query": operation, "variables": body or {}}
        response = await self._http.post(self._endpoint, json=payload)
        result = response.json()
        if "errors" in result:
            raise GraphQLError(result["errors"])
        return ProtocolResponse(data=result["data"], ...)
```

**SOAP Adapter** — handles XML envelope construction:
```python
class SOAPAdapter(ProtocolAdapter):
    async def request(self, operation, *, body=None, **kw):
        envelope = self._build_soap_envelope(operation, body)
        response = await self._http.post(self._wsdl_url, content=envelope,
                                          headers={"Content-Type": "text/xml"})
        return ProtocolResponse(data=self._parse_soap_response(response.content), ...)
```

**A connector declares its protocol:**
```python
class Shopify(BaseConnector):
    name = "shopify"
    protocol = ProtocolType.GRAPHQL

    @action("List products")
    async def list_products(self, limit: int = 10) -> PaginatedList[Product]:
        # self.adapter is a GraphQLAdapter — auto-selected from protocol declaration
        response = await self.adapter.request(
            "{ products(first: $limit) { edges { node { id title } } pageInfo { hasNextPage endCursor } } }",
            body={"limit": limit}
        )
        return self._parse_products(response.data)
```

### 3.4 Auth Provider System (Expanded)

The brainstorm's `AuthType` enum with 6 values is insufficient. Real world has 12+ auth patterns.

```python
# toolsconnector/runtime/auth/base.py

class AuthProvider(Protocol):
    """Pluggable auth provider. Each auth method implements this."""

    auth_type: str  # Identifier (e.g., "oauth2", "sigv4", "mtls")

    async def authenticate(self, request: AuthRequest) -> AuthResult:
        """Add auth to an outgoing request."""
        ...

    async def refresh(self) -> None:
        """Refresh credentials if expired."""
        ...

    async def validate(self) -> bool:
        """Check if current credentials are valid."""
        ...

    def needs_refresh(self) -> bool:
        """Check if credentials need refreshing."""
        ...

class AuthRequest(BaseModel):
    """Mutable request object that auth providers modify."""
    headers: dict[str, str] = {}
    params: dict[str, str] = {}
    body: Any = None

class AuthResult(BaseModel):
    """Result of authentication — modified request + metadata."""
    request: AuthRequest
    expires_at: datetime | None = None
    scopes: list[str] = []
```

**Auth provider implementations** (each is a separate module, optional install):

| Provider | Module | When to Use | Optional Dep |
|---|---|---|---|
| API Key | `auth/api_key.py` | Simple key-based APIs (OpenAI, SendGrid) | None |
| Bearer Token | `auth/bearer.py` | Pre-obtained tokens | None |
| Basic Auth | `auth/basic.py` | Legacy APIs, databases | None |
| OAuth 2.0 | `auth/oauth2.py` | Most SaaS (Google, Slack, Notion) | None |
| OAuth 2.0 + PKCE | `auth/oauth2_pkce.py` | Modern OAuth (required by OAuth 2.1) | None |
| OIDC | `auth/oidc.py` | SSO + identity (Auth0, Okta) | None |
| Service Account | `auth/service_account.py` | Google Cloud, Firebase | None |
| HMAC Signing | `auth/hmac.py` | Stripe webhooks, custom APIs | None |
| AWS SigV4 | `auth/sigv4.py` | All AWS services | None |
| mTLS | `auth/mtls.py` | Zero-trust, financial APIs | None |
| Custom | `auth/custom.py` | Base for custom providers | None |

**Connector declares supported auth:**
```python
class Gmail(BaseConnector):
    auth_providers = [
        OAuth2Provider(
            auth_url="https://accounts.google.com/o/oauth2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes={"read": ["gmail.readonly"], "send": ["gmail.send"]},
        ),
        ServiceAccountProvider(credential_format="json_keyfile"),
    ]
```

### 3.5 Pagination Strategy System

The brainstorm only has `PaginatedList` with a cursor. Real APIs use 6+ patterns.

```python
# toolsconnector/runtime/pagination/base.py

class PaginationStrategy(Protocol):
    """Pluggable pagination strategy."""

    def get_page_params(self, page_state: PageState) -> dict:
        """Return query params for the next page."""
        ...

    def parse_page_info(self, response: ProtocolResponse) -> PageState:
        """Extract pagination state from response."""
        ...

    def has_more(self, state: PageState) -> bool:
        """Check if more pages exist."""
        ...

class PageState(BaseModel):
    """Tracks pagination state across pages."""
    cursor: str | None = None
    offset: int | None = None
    page_number: int | None = None
    total_count: int | None = None
    has_more: bool = False
```

**Strategy implementations:**
```python
# Cursor-based (Slack, Stripe, Facebook)
class CursorPagination(PaginationStrategy):
    cursor_param: str = "cursor"      # query param name
    cursor_field: str = "next_cursor"  # response field

# Offset-based (legacy APIs)
class OffsetPagination(PaginationStrategy):
    offset_param: str = "offset"
    limit_param: str = "limit"
    total_field: str = "total"

# Page-number (older APIs)
class PageNumberPagination(PaginationStrategy):
    page_param: str = "page"
    per_page_param: str = "per_page"
    total_pages_field: str = "total_pages"

# Link-header (GitHub API)
class LinkHeaderPagination(PaginationStrategy):
    # Parses Link: <url>; rel="next" headers

# Token-based (Google APIs)
class TokenPagination(PaginationStrategy):
    token_param: str = "pageToken"
    token_field: str = "nextPageToken"
    items_field: str = "items"

# Keyset (high-performance APIs)
class KeysetPagination(PaginationStrategy):
    order_field: str = "id"
    direction: str = "asc"
```

**Connector declares its pagination:**
```python
class Gmail(BaseConnector):
    @action("List emails", pagination=TokenPagination(
        token_param="pageToken",
        token_field="nextPageToken",
        items_field="messages"
    ))
    async def list_emails(self, query: str = "is:unread") -> PaginatedList[Email]: ...
```

### 3.6 PaginatedList[T] (Enhanced)

```python
class PaginatedList(BaseModel, Generic[T]):
    """Universal paginated response. Works with ALL pagination strategies."""
    items: list[T]
    page_state: PageState            # Current pagination state
    total_count: int | None = None

    # Internal — set by runtime, not by connector author
    _strategy: PaginationStrategy | None = PrivateAttr(default=None)
    _fetch_next: Callable | None = PrivateAttr(default=None)

    @property
    def has_more(self) -> bool:
        return self.page_state.has_more

    # Sync iteration
    def __iter__(self) -> Iterator[T]:
        yield from self.items

    # Async iteration across all pages
    async def __aiter__(self) -> AsyncIterator[T]:
        page = self
        while True:
            for item in page.items:
                yield item
            if not page.has_more:
                break
            page = await page.anext_page()

    async def anext_page(self) -> "PaginatedList[T] | None":
        if not self.has_more or not self._fetch_next:
            return None
        return await self._fetch_next(self.page_state)

    async def collect(self, max_items: int = 1000) -> list[T]:
        """Collect all pages up to max_items."""
        all_items = list(self.items)
        page = self
        while page.has_more and len(all_items) < max_items:
            page = await page.anext_page()
            if page:
                all_items.extend(page.items)
        return all_items[:max_items]

    # Sync versions auto-generated
    def next_page(self) -> "PaginatedList[T] | None": ...
    def collect_sync(self, max_items: int = 1000) -> list[T]: ...
```

### 3.7 Error Hierarchy

```
ToolsConnectorError (base — all errors inherit this)
│   Fields: connector, action, code, message, retry_eligible,
│           retry_after_seconds, suggestion, details, upstream_status
│   Methods: to_dict(), to_json(), __str__()
│
├── AuthError — credential/token/scope failures
│   ├── TokenExpiredError        (code: AUTH_TOKEN_EXPIRED, retry: true after refresh)
│   ├── InvalidCredentialsError  (code: AUTH_INVALID_CREDENTIALS, retry: false)
│   ├── InsufficientScopeError   (code: AUTH_INSUFFICIENT_SCOPE, retry: false)
│   ├── RefreshFailedError       (code: AUTH_REFRESH_FAILED, retry: false)
│   └── MFARequiredError         (code: AUTH_MFA_REQUIRED, retry: false)
│
├── APIError — upstream API returned an error
│   ├── RateLimitError           (code: API_RATE_LIMITED, retry: true)
│   ├── NotFoundError            (code: API_NOT_FOUND, retry: false)
│   ├── ValidationError          (code: API_VALIDATION_FAILED, retry: false)
│   ├── ConflictError            (code: API_CONFLICT, retry: false)
│   ├── PermissionError          (code: API_PERMISSION_DENIED, retry: false)
│   ├── ServerError              (code: API_SERVER_ERROR, retry: true)
│   └── DeprecatedError          (code: API_DEPRECATED, retry: false)
│
├── TransportError — network/connection issues
│   ├── TimeoutError             (code: TRANSPORT_TIMEOUT, retry: true)
│   ├── ConnectionError          (code: TRANSPORT_CONNECTION_FAILED, retry: true)
│   └── DNSError                 (code: TRANSPORT_DNS_FAILED, retry: true)
│
├── ConnectorError — connector lifecycle issues
│   ├── ConnectorNotConfiguredError  (code: CONNECTOR_NOT_CONFIGURED)
│   ├── ConnectorInitError           (code: CONNECTOR_INIT_FAILED)
│   └── ActionNotFoundError          (code: CONNECTOR_ACTION_NOT_FOUND)
│
└── ConfigError — invalid configuration
    ├── InvalidConfigError       (code: CONFIG_INVALID)
    └── MissingConfigError       (code: CONFIG_MISSING_REQUIRED)
```

Every error is:
- A Python exception (catch with `except RateLimitError`)
- A dict (for JSON APIs: `error.to_dict()`)
- AI-readable (structured `code` + `suggestion` field)
- Retryable-aware (middleware can auto-retry based on `retry_eligible`)

### 3.8 BaseConnector Design

```python
class BaseConnector(ABC):
    """Abstract base for all connectors.

    A connector author subclasses this and:
    1. Sets class-level metadata (name, category, protocol, auth)
    2. Implements @action methods
    3. Optionally overrides lifecycle hooks
    """

    # --- Class-level declarations (set by connector authors) ---
    name: ClassVar[str]                           # "gmail"
    display_name: ClassVar[str]                   # "Gmail"
    category: ClassVar[ConnectorCategory]
    protocol: ClassVar[ProtocolType] = ProtocolType.REST
    base_url: ClassVar[str | None] = None
    auth_providers: ClassVar[list[AuthProvider]] = []
    rate_limit: ClassVar[RateLimitConfig | None] = None

    # --- Instance state (created by __init__) ---
    _adapter: ProtocolAdapter           # Protocol-specific adapter
    _auth_manager: AuthManager          # Auth lifecycle
    _keystore: KeyStore                 # Credential storage
    _middleware_pipeline: MiddlewarePipeline
    _storage: StorageBackend | None     # File handling
    _tenant_id: str | None
    _config: ConnectorConfig

    def __init__(
        self,
        *,
        credentials: CredentialSet | str | dict | None = None,
        keystore: KeyStore | None = None,
        middleware: list[Middleware] | None = None,
        storage: StorageBackend | None = None,
        tenant_id: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ): ...

    # --- Context managers ---
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *exc) -> None: ...

    # --- Lifecycle hooks (override in subclasses) ---
    async def _setup(self) -> None: ...
    async def _teardown(self) -> None: ...
    async def _health_check(self) -> HealthStatus: ...

    # --- Spec extraction (no instantiation needed) ---
    @classmethod
    def get_spec(cls) -> ConnectorSpec:
        """Extract the full connector specification.
        Used by: serve layer, codegen, documentation, conformance tests."""
        ...

    @classmethod
    def get_actions(cls) -> dict[str, ActionMeta]: ...

    # --- Internal API for connector implementations ---
    @property
    def adapter(self) -> ProtocolAdapter:
        """Protocol adapter (REST, GraphQL, etc.) — use this in actions."""
        ...
```

### 3.9 @action Decorator (The Engine)

```python
def action(
    description: str,
    *,
    requires_scope: str | None = None,
    dangerous: bool = False,
    idempotent: bool = False,
    pagination: PaginationStrategy | None = None,
    tags: list[str] | None = None,
    rate_limit_weight: int = 1,           # Some actions cost more
) -> Callable:
    """Marks a method as a connector action.

    What this decorator does at class definition time:
    1. Parses method signature → builds Pydantic input model dynamically
    2. Parses Google-style docstring → extracts parameter descriptions
    3. Generates JSON Schema from the Pydantic model
    4. Creates sync wrapper from async implementation
    5. Stores ActionMeta for introspection by serve layer
    6. Wires pagination strategy into return type
    7. Registers action in connector's _actions registry
    """
```

**Sync/async bridge — connector author writes async, users get both:**
```python
# Connector author writes:
class Gmail(BaseConnector):
    @action("List emails")
    async def list_emails(self, query: str = "is:unread") -> PaginatedList[Email]:
        response = await self.adapter.request("/messages", params={"q": query})
        ...

# Users can call either way:
emails = gmail.list_emails(query="is:unread")        # sync (auto-generated)
emails = await gmail.alist_emails(query="is:unread")  # async (prefixed with 'a')
```

### 3.10 Middleware Pipeline

```python
class Middleware(Protocol):
    async def __call__(
        self, context: ActionContext, call_next: CallNext
    ) -> ActionResult: ...

class ActionContext(BaseModel):
    """Everything about the current action invocation."""
    connector_name: str
    action_name: str
    args: dict[str, Any]
    auth_state: AuthState
    tenant_id: str | None
    request_id: str          # UUID for tracing
    attempt: int = 1         # Retry attempt number
    metadata: dict[str, Any] = {}
```

**Default pipeline order:**
```
Request → LoggingMiddleware → AuthMiddleware → RateLimitMiddleware
        → RetryMiddleware → IdempotencyMiddleware → [Action Execution]
        → Response flows back through middleware in reverse
```

Middleware is composable. Users prepend/append custom middleware:
```python
gmail = Gmail(
    credentials=creds,
    middleware=[
        CostTrackingMiddleware(budget_cents=100),
        CacheMiddleware(ttl=300, cache_actions=["list_emails"]),
        HumanApprovalMiddleware(require_approval=["send_email", "delete_email"]),
    ]
)
```

### 3.11 Type System

**Decision: Pydantic V2** for all data models.

Why:
- `.model_json_schema()` generates JSON Schema → drives entire serve layer + spec extraction
- Validation built-in → connector inputs validated before API calls
- Serialization → `.model_dump()` / `.model_dump_json()`
- `ConfigDict(frozen=True)` for immutable response types
- V2 has Rust core — fast enough for hot paths

**Conventions:**
- Connector input types: mutable models (user constructs them)
- Connector output types: frozen models (immutable responses)
- Framework types (PaginatedList, FileRef, errors): in `toolsconnector/types/`
- Connector-specific types: in `connectors/{tool}/types.py`

### 3.12 FileRef & Storage

```python
class FileRef(BaseModel):
    """Universal file reference. Connectors accept/return these instead of raw bytes."""
    uri: str                    # "s3://bucket/file.pdf", "file:///tmp/doc.pdf"
    filename: str
    mime_type: str
    size_bytes: int | None = None
    metadata: dict[str, str] = {}

class StorageBackend(Protocol):
    async def read(self, uri: str) -> AsyncIterator[bytes]: ...
    async def write(self, uri: str, stream: AsyncIterator[bytes],
                    mime_type: str) -> FileRef: ...
    async def exists(self, uri: str) -> bool: ...
    async def delete(self, uri: str) -> None: ...
```

Built-in: `LocalStorageBackend`, `InMemoryStorageBackend`
Optional extras: `S3StorageBackend`, `GCSStorageBackend`, `AzureBlobStorageBackend`

### 3.13 KeyStore

```python
class KeyStore(Protocol):
    """Pluggable credential storage. All methods async."""
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
```

Key naming: `{connector}:{tenant_id}:{credential_type}`
Example: `gmail:user-123:access_token`

| Implementation | Install | Use Case |
|---|---|---|
| InMemoryKeyStore | core | Development, testing |
| EnvironmentKeyStore | core | CI/CD, containers, read-only |
| LocalFileKeyStore | core | Local dev (Fernet encrypted) |
| VaultKeyStore | `[vault]` extra | Enterprise (HashiCorp Vault) |
| AWSSecretsKeyStore | `[aws]` extra | AWS deployments |

---

## Part 4: Serve Layer

### 4.1 MCP Server Generation

```python
# One-line MCP server from any set of connectors
from toolsconnector.serve import mcp
mcp.serve([Gmail, Slack, GitHub], port=3000, transport="stdio")
```

Translation mapping (ConnectorSpec → MCP):
| ConnectorSpec | MCP Protocol |
|---|---|
| `action.description` | Tool description |
| `action.input_schema` (JSON Schema) | Tool inputSchema |
| Return type schema | Tool result format |
| `action.dangerous` | Tool annotation (destructive hint) |
| `PaginatedList` | Cursor in result metadata |
| `ToolsConnectorError` | `isError: true` + structured content |
| `action.requires_scope` | Capability annotation |

### 4.2 Schema Generators

```python
from toolsconnector.serve.schema import to_openai, to_anthropic, to_gemini, to_langchain

tools_openai = to_openai([gmail, slack])       # OpenAI function calling
tools_anthropic = to_anthropic([gmail, slack])  # Anthropic tool use
tools_gemini = to_gemini([gmail, slack])        # Google Gemini
tools_langchain = to_langchain([gmail, slack])  # LangChain tools
```

All read from the same `ConnectorSpec.actions[*].input_schema`. Format differences are thin adapter code.

### 4.3 REST API (Optional)

```python
from toolsconnector.serve.rest import create_app
app = create_app([Gmail, Slack])  # Returns ASGI app

# Routes:
# GET  /api/v1/connectors              → list installed connectors
# GET  /api/v1/{connector}/actions     → list actions
# POST /api/v1/{connector}/{action}    → execute action
# GET  /api/v1/spec                    → full OpenAPI spec
```

### 4.4 CLI

```bash
tc list                               # List installed connectors
tc gmail actions                      # List Gmail actions
tc gmail list-emails --query "is:unread"  # Execute action
tc serve mcp gmail slack --port 3000  # Start MCP server
tc serve rest gmail slack --port 8000 # Start REST server
tc spec gmail --format yaml           # Export connector spec
tc health gmail                       # Run health check
```

---

## Part 5: Multi-Language Strategy

### Phase 1 (Now): Python as Reference Implementation
- Build everything in Python
- `ConnectorSpec` (Pydantic models) generates JSON Schema automatically
- Conformance tests written as JSON fixtures in `spec/conformance/`
- This IS the spec — extracted programmatically

### Phase 2 (After v1.0): Formalize Specification
- Extract standalone `SPEC.md` from working Python code
- Publish `spec/schemas/*.json` (JSON Schema files for connector, action, auth, error)
- Conformance test suite as language-agnostic JSON test cases

### Phase 3: TypeScript SDK
- First non-Python SDK
- Implements same `BaseConnector` / `@action` pattern using TypeScript idioms
- Reads same connector spec files
- Passes same conformance tests
- Published as `@toolsconnector/core` on npm

### Phase 4+: Go, Java, Rust SDKs
- Each follows the spec
- Each uses language-native patterns (Go interfaces, Java annotations, Rust traits)
- All pass the same conformance test suite

### Repo Structure for Multi-Language

```
toolsconnector/                    # GitHub org or monorepo
├── spec/                          # THE specification (language-agnostic)
│   ├── SPEC.md                    # Human-readable specification
│   ├── schemas/                   # JSON Schema files
│   │   ├── connector.schema.json
│   │   ├── action.schema.json
│   │   ├── auth.schema.json
│   │   ├── error.schema.json
│   │   └── pagination.schema.json
│   └── conformance/               # Language-agnostic test cases
│       ├── test-cases.json
│       └── fixtures/              # Recorded API responses
│
├── python/                        # Python SDK (reference implementation)
│   └── (current project)
│
├── typescript/                    # TypeScript SDK (Phase 3)
├── go/                            # Go SDK (Phase 4)
└── java/                          # Java SDK (Phase 4)
```

Each SDK must:
1. Implement `BaseConnector` equivalent in its language
2. Support all auth providers
3. Support all pagination strategies
4. Pass conformance test suite
5. Generate MCP/schema output matching the spec

---

## Part 6: Security & Governance (Foundation-Grade)

### 6.1 Security Policy

**SECURITY.md** (created at project init):
- Vulnerability disclosure: sachin.worldnet@gmail.com (prefer GitHub Private Vulnerability Reporting — see SECURITY.md)
- Response SLA: acknowledge within 48h, patch within 14 days for critical
- CVE process: request CVE for any auth/credential vulnerability
- Security audit: annual third-party audit once funded
- Dependency audit: `pip-audit` in CI, Dependabot alerts

**Threat Model:**
| Threat | Mitigation |
|---|---|
| Credential leakage | KeyStore abstraction, never log tokens, Fernet encryption at rest |
| Supply chain attack | Signed releases, SBOM, pinned dependencies, `pip-audit` |
| Token replay | Token expiry validation, refresh before use, nonce support |
| Injection via connector | Input validation via Pydantic, parameterized queries |
| Malicious connector contribution | Conformance tests, automated review, maintainer sign-off |

### 6.2 Governance

**RFC Process:**
1. Author opens GitHub Discussion with `[RFC]` prefix
2. 2-week comment period
3. Spec maintainer + 2 language leads must approve
4. Implementation PRs reference the RFC
5. Conformance tests added with implementation

**Decision Framework:**
- Spec changes: RFC required (affects all languages)
- Connector additions: PR + conformance tests (no RFC needed)
- Core runtime changes: RFC if breaking, PR if additive
- Bug fixes: PR with test

**Release Cadence:**
- Spec: quarterly (x.y.0 releases)
- Python SDK: monthly (follows spec + language-specific fixes)
- Other SDKs: follow spec quarterly + independent patches

**Versioning:**
- Spec version: SemVer (1.0.0, 1.1.0, 2.0.0)
- SDK version: tracks spec major.minor, independent patch
- Example: Spec 1.2 → Python SDK 1.2.3, TypeScript SDK 1.2.1

### 6.3 Quality Gates

| Gate | Tool | When |
|---|---|---|
| Type checking | mypy --strict | Every PR |
| Linting | ruff | Every PR |
| Unit tests | pytest | Every PR |
| Contract tests | VCR fixtures | Every PR |
| Conformance tests | Custom framework | Every PR |
| Import boundary check | Custom rule | Every PR |
| Dependency audit | pip-audit | Weekly |
| Integration tests | Real APIs | Nightly (Tier-1 only) |
| Security scan | bandit + safety | Every PR |
| SBOM generation | cyclonedx-bom | Every release |
| Release signing | GPG | Every release |

---

## Part 7: Connector Health Agent System

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    HEALTH AGENT SYSTEM                        │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  WATCH Layer (GitHub Actions — scheduled)            │    │
│  │                                                      │    │
│  │  Per connector:                                      │    │
│  │  ├── Monitor SDK GitHub releases (RSS/API)           │    │
│  │  ├── Diff OpenAPI specs (if published)               │    │
│  │  ├── Scrape API changelog pages                      │    │
│  │  ├── Run contract tests against live API              │    │
│  │  └── Check dependency vulnerability advisories       │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │  DETECT Layer (Claude Sonnet API)                    │    │
│  │                                                      │    │
│  │  Input: changelog diff + our connector code          │    │
│  │  Output: classification                              │    │
│  │  ├── NO_IMPACT    → log and skip                     │    │
│  │  ├── ADDITIVE     → new endpoints/params available   │    │
│  │  ├── DEPRECATION  → feature going away (timeline)    │    │
│  │  ├── BREAKING     → parameter removed, auth changed  │    │
│  │  ├── RATE_CHANGE  → rate limits updated              │    │
│  │  └── CRITICAL     → API removed, auth broken         │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │  ACT Layer (Claude Opus API)                         │    │
│  │                                                      │    │
│  │  ADDITIVE/DEPRECATION:                               │    │
│  │  └── Auto-generate PR with connector update          │    │
│  │                                                      │    │
│  │  BREAKING:                                           │    │
│  │  └── Create detailed issue with:                     │    │
│  │      ├── What changed                                │    │
│  │      ├── Impact analysis (which actions affected)    │    │
│  │      ├── Suggested fix                               │    │
│  │      └── Migration guide for users                   │    │
│  │                                                      │    │
│  │  CRITICAL:                                           │    │
│  │  └── Alert maintainers + create P0 issue             │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Schedule:** Tier-1 connectors weekly, Tier-2 biweekly, Tier-3 monthly.

---

## Part 8: Package & Dependency Management

### pyproject.toml

```toml
[project]
name = "toolsconnector"
requires-python = ">=3.9"
license = "Apache-2.0"
dependencies = [
    "pydantic>=2.0,<3.0",
    "httpx>=0.25.0,<1.0",
    "docstring-parser>=0.15",
]

[project.optional-dependencies]
# --- Connectors (Tier 1) ---
gmail = ["google-api-python-client>=2.0", "google-auth>=2.0", "google-auth-oauthlib>=1.0"]
gdrive = ["google-api-python-client>=2.0", "google-auth>=2.0"]
gcalendar = ["google-api-python-client>=2.0", "google-auth>=2.0"]
slack = ["slack-sdk>=3.20"]
notion = ["notion-client>=2.0"]
github = ["PyGithub>=2.0"]
jira = ["jira>=3.5"]

# --- Connectors (Tier 2) ---
outlook = ["msal>=1.20", "msgraph-sdk>=1.0"]
teams = ["msal>=1.20", "msgraph-sdk>=1.0"]
confluence = ["atlassian-python-api>=3.30"]
asana = ["asana>=5.0"]
s3 = ["boto3>=1.28"]
hubspot = ["hubspot-api-client>=8.0"]

# --- Protocol adapters ---
graphql = ["gql>=3.4", "aiohttp>=3.8"]
soap = ["zeep>=4.2"]
grpc = ["grpcio>=1.50", "protobuf>=4.0"]
websocket = ["websockets>=12.0"]

# --- KeyStore extras ---
vault = ["hvac>=1.0"]
aws-keystore = ["boto3>=1.28"]

# --- Storage extras ---
s3-storage = ["boto3>=1.28"]
gcs-storage = ["google-cloud-storage>=2.0"]

# --- Serve layer ---
mcp = ["mcp>=1.0"]
rest = ["starlette>=0.27", "uvicorn>=0.23"]

# --- Category bundles ---
google = ["toolsconnector[gmail,gdrive,gcalendar]"]
microsoft = ["toolsconnector[outlook,teams]"]
communication = ["toolsconnector[gmail,slack]"]
project-mgmt = ["toolsconnector[jira,asana]"]

# --- Development ---
dev = ["pytest>=7.0", "pytest-asyncio>=0.21", "respx>=0.20", "vcrpy>=6.0",
       "ruff>=0.1", "mypy>=1.5", "bandit>=1.7", "pip-audit>=2.6"]

# --- Everything ---
all = ["toolsconnector[gmail,slack,github,notion,jira,gdrive,gcalendar,mcp,rest]"]

[project.scripts]
tc = "toolsconnector.serve.cli:main"

[project.entry-points."toolsconnector.connectors"]
gmail = "toolsconnector.connectors.gmail:Gmail"
slack = "toolsconnector.connectors.slack:Slack"
github = "toolsconnector.connectors.github:GitHub"
# ... each connector registers here for CLI/serve discovery
```

### Import Boundary Rules (enforced by CI)

```
spec/        → imports NOTHING else (pure types)
runtime/     → imports spec/ only
types/       → imports spec/ only
errors/      → imports spec/ only
keystore/    → imports spec/ only (implements Protocol)
connectors/  → imports runtime/, types/, errors/ (never serve/, never other connectors/)
serve/       → imports spec/, types/, errors/ (reads metadata via get_spec(), never imports connectors/)
codegen/     → imports spec/ only
health/      → imports spec/ only
```

---

## Part 9: Phased Implementation Roadmap

### Phase -1: Agent Army Infrastructure (Week 0)
**Goal:** Build the orchestrator so all subsequent phases run autonomously.

Build order (done manually in Claude Code, not by orchestrator yet):
1. `.agents/orchestrator/config.py` — configuration loading
2. `.agents/orchestrator/taskboard.py` — YAML task board parser
3. `.agents/orchestrator/state.py` — SQLite state management
4. `.agents/orchestrator/tools/` — all tool definitions (filesystem, shell, git, test)
5. `.agents/orchestrator/runner.py` — Claude API agent runner with tool loop
6. `.agents/orchestrator/engine.py` — DAG executor with parallel dispatch
7. `.agents/orchestrator/reporter.py` — terminal progress reporting
8. `.agents/orchestrator/main.py` — CLI entry point
9. `.agents/orchestrator/prompts/` — system prompt templates per agent type
10. `.agents/taskboard.yaml` — Phase 0 task board (pre-populated)
11. Update all `.agents/skills/` SKILL.md files for the new architecture
12. Add new skills: `test_engineer`, `documenter`, `reviewer`

**Exit criteria:**
- `python -m agents.orchestrator run --phase 0 --dry-run` shows correct task DAG
- A single test task runs successfully (e.g., "create a hello.py file")
- Agent gets tools, executes them, completes task
- State persisted to SQLite

**Note:** This phase is done by YOU (Sachin) + one Claude Code session. After this, Phase 0+ runs autonomously.

### Phase 0: Core Primitive (Weeks 1-4)
**Goal:** The foundational runtime + one working connector.

Build order (executed by orchestrator — `python -m agents.orchestrator run --phase 0`):
1. `spec/` — all specification types (ConnectorSpec, ActionSpec, AuthSpec, etc.)
2. `errors/` — full error hierarchy
3. `types/` — PaginatedList, FileRef, CredentialSet
4. `keystore/` — KeyStore protocol + InMemoryKeyStore + EnvironmentKeyStore
5. `runtime/transport/` — HTTP transport (httpx)
6. `runtime/auth/` — AuthProvider protocol + API key + OAuth2 providers
7. `runtime/protocol/` — ProtocolAdapter protocol + RESTAdapter
8. `runtime/pagination/` — PaginationStrategy protocol + TokenPagination + CursorPagination
9. `runtime/middleware/` — pipeline + auth + retry + rate limit + logging middleware
10. `runtime/base.py` — BaseConnector
11. `runtime/action.py` — @action decorator with full introspection
12. `runtime/_sync.py` — sync/async bridge
13. `connectors/gmail/` — Gmail connector (full capability)
14. `pyproject.toml` + project scaffolding

**Exit criteria:**
- `gmail.list_emails()` works end-to-end (sync and async)
- `Gmail.get_spec()` returns valid ConnectorSpec
- Error handling works correctly (rate limits, auth failures)
- Token refresh works transparently
- 90%+ test coverage on runtime/

### Phase 1: Serve Layer + Expand (Weeks 5-8)
**Goal:** MCP server, CLI, schema generators, 2 more connectors.

Build:
1. `serve/mcp.py` — MCP server generation from ConnectorSpec
2. `serve/schema.py` — OpenAI/Anthropic/Gemini schema generators
3. `serve/cli.py` — `tc` CLI command
4. `connectors/slack/` — Slack connector (WebSocket-capable)
5. `connectors/github/` — GitHub connector (Link-header pagination)
6. Conformance test framework

**Exit criteria:**
- `tc serve mcp gmail slack` starts MCP server, works with Claude Desktop
- `tc gmail list-emails --query "is:unread"` works from CLI
- Conformance tests pass for all 3 connectors
- Schema generators produce valid OpenAI/Anthropic tool definitions

### Phase 2: Protocol Diversity + Scale (Weeks 9-13)
**Goal:** Prove the architecture handles diverse protocols and patterns.

Build:
1. `runtime/protocol/graphql.py` — GraphQL adapter
2. `connectors/shopify/` or `connectors/linear/` — GraphQL connector (proves GraphQL adapter)
3. `connectors/notion/` — Notion connector
4. `connectors/jira/` — Jira connector
5. `connectors/gdrive/` — Google Drive (file handling with FileRef)
6. `connectors/gcalendar/` — Google Calendar
7. `serve/rest.py` — REST API exposure
8. `keystore/local.py` — LocalFileKeyStore (Fernet encrypted)
9. Multi-tenancy support in BaseConnector

**Exit criteria:**
- GraphQL connector works end-to-end
- File upload/download works via FileRef
- 7 connectors total, all passing conformance
- Multi-tenant credential isolation works

### Phase 3: AgentStore Integration + Health Agent (Weeks 14-18)
**Goal:** Production-harden for AgentStore, start Health Agent.

Build:
1. `toolsconnector-mcp/` — separate package with enhanced MCP server
2. Multi-tenant MCP serving
3. `health/watcher.py` — SDK release monitoring
4. `health/analyzer.py` — AI-powered change classification
5. `health/reporter.py` — PR/issue generation
6. GitHub Actions workflows for health monitoring
7. Tier-2 connectors: Outlook, Teams, Confluence, Asana
8. Security hardening: SBOM, signed releases, pip-audit in CI

**Exit criteria:**
- AgentStore staging uses ToolsConnector for all tool integrations
- Health Agent detects a real SDK update and classifies it correctly
- 12+ connectors, all passing conformance
- SECURITY.md + vulnerability disclosure process live

### Phase 4: Public Launch (Weeks 19-24)
**Goal:** v1.0 public release on PyPI.

Build:
1. Remaining Tier-2 connectors: S3, HubSpot
2. Additional auth providers: HMAC, SigV4 (for AWS connectors)
3. LangChain adapter
4. CrewAI adapter
5. Comprehensive documentation site
6. Contributor guide + connector authoring tutorial
7. `spec/` directory with extracted JSON Schema files
8. Conformance test suite publishable for other language SDKs
9. RFC process documentation
10. Public launch: PyPI, GitHub, documentation site

**Exit criteria:**
- `pip install "toolsconnector[gmail]"` + send email in <5 minutes
- 15+ connectors across 5+ categories
- Documentation complete (quickstart, API reference, connector authoring guide)
- RFC process live, CONTRIBUTING.md, governance defined
- Conformance test suite ready for TypeScript SDK to target

### Phase 5: Multi-Language + Ecosystem (Months 7-18)
**Goal:** TypeScript SDK, community growth, Foundation readiness.

Build:
1. Formalize spec into standalone `SPEC.md` + JSON Schema files
2. TypeScript SDK (`@toolsconnector/core` on npm)
3. Community connector pipeline (submission → AI review → merge)
4. Health Agent fully automated
5. SOAP adapter (for enterprise connectors)
6. WebSocket adapter (for real-time connectors)
7. 30+ connectors, including community contributions
8. Foundation governance evaluation

---

## Part 10: Verification Plan

### Phase 0 Verification
```bash
# 1. Type check
mypy toolsconnector/ --strict

# 2. Lint
ruff check toolsconnector/

# 3. Unit tests
pytest tests/unit/ -v --cov=toolsconnector --cov-report=term-missing

# 4. Contract tests (VCR fixtures)
pytest tests/contract/ -v

# 5. Conformance tests
pytest tests/conformance/ -v

# 6. Integration smoke test
python -c "
from toolsconnector.connectors.gmail import Gmail
gmail = Gmail(credentials='path/to/service-account.json')
emails = gmail.list_emails(query='is:unread', limit=3)
print(f'Got {len(emails.items)} emails')
print(f'Has more: {emails.has_more}')

spec = Gmail.get_spec()
print(f'Spec version: {spec.spec_version}')
print(f'Actions: {list(spec.actions.keys())}')
print(f'Auth types: {[a.type for a in spec.auth.supported]}')
"

# 7. Import boundary check
python -c "
import ast, sys
# Verify core/ doesn't import connectors/ or serve/
# (automated in CI via custom ruff rule)
"
```

### Phase 1 Verification
```bash
# MCP server test
tc serve mcp gmail slack --transport stdio
# → Connect Claude Desktop → "List my unread emails" → works

# CLI test
tc gmail list-emails --query "is:unread" --limit 5

# Schema generation test
python -c "
from toolsconnector.connectors.gmail import Gmail
from toolsconnector.serve.schema import to_openai
tools = to_openai([Gmail])
import json; print(json.dumps(tools, indent=2))
"
```

---

## Part 11: Claude Agent & Sub-Agent Team Architecture

### 11.1 The Agent Army Vision

All implementation work is executed by a structured team of Claude agents. The human (Sachin) acts as the Product Owner — setting priorities, reviewing output, and making final calls. The agents do the engineering.

### 11.2 Agent Hierarchy

```
┌──────────────────────────────────────────────────────────────────┐
│                    PRODUCT OWNER (Sachin)                         │
│  Sets priorities, reviews output, approves releases              │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    LEAD ENGINEER (Main Claude Session)            │
│                                                                   │
│  Responsibilities:                                                │
│  ├── Reads roadmap & current phase (codevira get_roadmap)        │
│  ├── Breaks work into tasks (TodoWrite)                          │
│  ├── Delegates to sub-agents based on task domain                │
│  ├── Reviews sub-agent output for quality & consistency          │
│  ├── Integrates work across agents (merge conflicts, interfaces) │
│  ├── Makes architectural decisions within approved plan          │
│  ├── Reports progress to Product Owner                           │
│  └── Escalates blockers that need human judgment                 │
│                                                                   │
│  Rules:                                                           │
│  ├── ALWAYS check plan before starting work                      │
│  ├── NEVER modify spec/ without RFC discussion                   │
│  ├── ALWAYS run conformance tests after connector changes        │
│  └── Delegate to sub-agents for parallel work                    │
└───┬──────┬──────┬──────┬──────┬──────┬──────┬────────────────────┘
    │      │      │      │      │      │      │
    ▼      ▼      ▼      ▼      ▼      ▼      ▼
```

### 11.3 Sub-Agent Definitions

Each sub-agent has a clear domain, skill file, and rules. They are launched via the `Agent` tool from the Lead Engineer session.

---

#### Agent 1: `principal-architect`
**Skill file:** `.agents/skills/principal_architect/SKILL.md`
**Domain:** `spec/`, `runtime/`, `types/`, `errors/`
**Responsibility:** Design and build the core primitive — BaseConnector, @action, protocol adapters, auth providers, pagination strategies, middleware pipeline, error hierarchy.

**When to invoke:**
- Building any file in `spec/`, `runtime/`, `types/`, `errors/`
- Designing new protocol adapters or auth providers
- Reviewing cross-cutting architecture decisions
- Resolving import boundary violations

**Rules:**
- MUST maintain separation: no tool-specific logic in runtime/
- MUST keep dependencies minimal (only pydantic, httpx, docstring-parser)
- Every protocol adapter MUST implement `ProtocolAdapter` protocol
- Every auth provider MUST implement `AuthProvider` protocol
- Every pagination strategy MUST implement `PaginationStrategy` protocol
- All public types MUST generate valid JSON Schema via `.model_json_schema()`

**Output expectations:**
- Fully typed Python 3.9+ code
- Google-style docstrings on every public class/method
- Unit tests for every module
- Import boundary compliance verified

---

#### Agent 2: `connector-implementer`
**Skill file:** `.agents/skills/connector_implementer/SKILL.md`
**Domain:** `connectors/{tool_name}/`
**Responsibility:** Build individual tool connectors. One agent invocation per connector (can run multiple in parallel for independent connectors).

**When to invoke:**
- Building a new connector (Gmail, Slack, GitHub, etc.)
- Updating an existing connector (API changes, new actions)
- Fixing connector bugs

**Rules:**
- MUST read the tool's official API documentation before implementing
- MUST use `@action` decorator on every public method
- MUST type all inputs and outputs with Pydantic models in `types.py`
- MUST declare auth_providers, protocol, rate_limit on the class
- MUST declare pagination strategy per action
- MUST NOT import from other connectors or from `serve/`
- MUST NOT exceed 500 lines per file (split into connector.py + types.py + helpers.py)
- MUST write unit tests with mocked HTTP (respx)
- MUST write contract test fixtures (VCR recordings)
- Docstrings become LLM function descriptions — write them as if explaining to an AI agent

**Output expectations per connector:**
```
connectors/{tool}/
├── __init__.py          # Re-export: from .connector import ToolName
├── connector.py         # < 500 lines, all @action methods
├── types.py             # Pydantic models for tool-specific types
├── helpers.py           # Optional: shared utilities
└── tests/
    ├── test_connector.py
    ├── test_types.py
    └── fixtures/        # VCR recorded responses
```

**Parallelization:** Multiple connector-implementer agents can run simultaneously for independent connectors. Example: Gmail agent + Slack agent + GitHub agent in parallel.

---

#### Agent 3: `serve-builder`
**Skill file:** `.agents/skills/mcp_generator/SKILL.md` (expanded scope)
**Domain:** `serve/`, `toolsconnector-mcp/`
**Responsibility:** Build the exposure layer — MCP server generation, REST API, CLI, schema generators for OpenAI/Anthropic/Gemini, framework adapters (LangChain, CrewAI).

**When to invoke:**
- Building MCP server generation
- Building CLI (`tc` command)
- Building schema generators
- Building REST API exposure
- Building framework adapters (LangChain, CrewAI)
- Building `toolsconnector-mcp` package

**Rules:**
- MUST only read connector metadata via `Connector.get_spec()` — never import connector internals
- MUST NOT add connector-specific logic in serve/ (it's generic)
- MCP output MUST comply with latest MCP specification
- Schema output MUST be valid per target framework's spec (OpenAI, Anthropic, Gemini)
- CLI MUST discover connectors via entry points, not hardcoded imports

---

#### Agent 4: `test-engineer`
**Domain:** `tests/`, conformance framework, CI configuration
**Responsibility:** Build and maintain the testing infrastructure — unit test patterns, contract test framework (VCR), conformance test suite, CI/CD pipelines.

**When to invoke:**
- Setting up test infrastructure for a new phase
- Building the conformance test framework
- Writing integration tests
- Setting up GitHub Actions CI/CD
- Auditing test coverage

**Rules:**
- Unit tests: MUST use `respx` for HTTP mocking, `pytest-asyncio` for async
- Contract tests: MUST use VCR.py for recorded fixtures
- Conformance tests: MUST be language-agnostic (JSON test case definitions)
- MUST verify import boundaries in CI
- MUST run `mypy --strict`, `ruff`, `bandit`, `pip-audit` in CI
- Integration tests: ONLY for Tier-1 connectors, ONLY in nightly CI

**Output expectations:**
```
tests/
├── unit/                    # Mocked, fast, every PR
│   ├── runtime/
│   ├── connectors/
│   ├── serve/
│   └── keystore/
├── contract/                # VCR fixtures, every PR
│   └── connectors/
├── conformance/             # Structural validation, every PR
│   ├── framework.py         # Conformance test framework
│   ├── test_connector_structure.py
│   ├── test_import_boundaries.py
│   └── test_spec_generation.py
├── integration/             # Real APIs, nightly
│   └── connectors/
└── conftest.py
```

---

#### Agent 5: `health-watcher`
**Skill file:** `.agents/skills/health_watcher/SKILL.md`
**Domain:** `health/`, `.github/workflows/connector-health.yml`
**Responsibility:** Build the connector health monitoring system — upstream SDK/API monitoring, AI-powered change classification, automated PR/issue generation.

**When to invoke:**
- Building the health monitoring pipeline
- Setting up GitHub Actions for health checks
- Investigating a reported upstream API change
- Generating migration patches for SDK updates

**Rules:**
- MUST check official SDK repos and changelogs before making changes
- MUST classify changes as: NO_IMPACT, ADDITIVE, DEPRECATION, BREAKING, CRITICAL
- MUST generate surgical fixes (minimal diff), not full rewrites
- Auto-PRs for ADDITIVE changes only — BREAKING requires human review
- MUST include migration guide in PR description for any breaking change

---

#### Agent 6: `documenter`
**Domain:** Documentation, docstrings, examples, contributor guides
**Responsibility:** Write and maintain all documentation — README, quickstart, API reference, connector authoring guide, architecture docs, CONTRIBUTING.md.

**When to invoke:**
- After a phase is complete (document what was built)
- When adding a new connector (document its usage)
- When changing public APIs (update docs)
- When preparing for public launch

**Rules:**
- Documentation MUST be accurate to current code (verify by reading source)
- Examples MUST be runnable (not pseudo-code)
- Connector docs MUST show both sync and async usage
- MUST update CHANGELOG.md with every significant change
- NEVER write docs for unimplemented features

---

#### Agent 7: `reviewer`
**Domain:** Cross-cutting quality assurance
**Responsibility:** Review code for quality, consistency, security, and spec compliance. Acts as the "second pair of eyes" before merging.

**When to invoke:**
- After any agent completes significant work
- Before marking a phase as complete
- When checking cross-agent integration (do connectors work with serve layer?)
- Security review before releases

**Review checklist:**
- [ ] All types fully annotated (no `Any`)
- [ ] Import boundaries respected
- [ ] Docstrings complete (Google style)
- [ ] Error handling uses framework error types
- [ ] No credentials in code
- [ ] Tests exist and pass
- [ ] Conformance tests pass
- [ ] Spec generation works (`Connector.get_spec()`)
- [ ] Lines < 100 chars, files < 500 lines
- [ ] No unnecessary dependencies

---

### 11.4 Agent Coordination Protocol

#### Session Start
```
1. Lead Engineer reads roadmap (codevira get_roadmap or plan file)
2. Lead Engineer identifies current phase and pending tasks
3. Lead Engineer breaks work into agent-assignable tasks
4. Lead Engineer launches sub-agents (parallel where independent)
```

#### Task Assignment Pattern
```python
# Lead Engineer decides which agent to invoke based on file paths:

if task involves spec/ or runtime/ or types/ or errors/:
    → Launch principal-architect agent

if task involves connectors/{tool}/:
    → Launch connector-implementer agent (one per connector, parallelizable)

if task involves serve/ or toolsconnector-mcp/:
    → Launch serve-builder agent

if task involves tests/ or CI:
    → Launch test-engineer agent

if task involves health/ or upstream monitoring:
    → Launch health-watcher agent

if task involves docs/ or README or CHANGELOG:
    → Launch documenter agent

if task is "review the work done so far":
    → Launch reviewer agent
```

#### Parallel Execution Rules
```
CAN run in parallel (independent domains):
├── Multiple connector-implementer agents (different connectors)
├── test-engineer + documenter (after implementation complete)
├── connector-implementer + serve-builder (if spec/ is stable)

MUST run sequentially (dependencies):
├── principal-architect BEFORE connector-implementer (core must exist first)
├── principal-architect BEFORE serve-builder (spec types must exist)
├── connector-implementer BEFORE test-engineer (need code to test)
├── All agents BEFORE reviewer (need code to review)
```

#### Phase Completion Protocol
```
1. All assigned agents complete their work
2. Lead Engineer launches reviewer agent for quality check
3. Lead Engineer launches test-engineer to run full test suite
4. Lead Engineer verifies exit criteria for the phase
5. Lead Engineer reports to Product Owner
6. Product Owner approves → advance to next phase
```

### 11.5 Agent Skill Files (Updated)

The existing `.agents/skills/` directory needs to be expanded:

```
.agents/skills/
├── principal_architect/SKILL.md    # Updated with new architecture
├── connector_implementer/SKILL.md  # Updated with new patterns
├── mcp_generator/SKILL.md          # Renamed scope → serve_builder
├── health_watcher/SKILL.md         # Updated with health pipeline
├── test_engineer/SKILL.md          # NEW
├── documenter/SKILL.md             # NEW
└── reviewer/SKILL.md               # NEW
```

### 11.6 Agent Invocation Examples

**Phase 0 — Building the core:**
```
Session starts:
  Lead reads plan → Phase 0 tasks

  Step 1: Launch principal-architect (foreground)
    "Build spec/ module: ConnectorSpec, ActionSpec, AuthSpec, PaginationSpec,
     ErrorSpec. All Pydantic V2 models with JSON Schema generation."

  Step 2: Launch principal-architect (foreground)
    "Build runtime/ core: BaseConnector, @action decorator, AuthManager,
     ProtocolAdapter protocol, RESTAdapter, middleware pipeline."

  Step 3: Launch principal-architect (foreground)
    "Build types/ and errors/ modules."

  Step 4: Launch connector-implementer (foreground)
    "Build Gmail connector in connectors/gmail/. Use RESTAdapter.
     Implement list_emails, send_email, get_email, search_emails.
     Full types in types.py."

  Step 5: Launch test-engineer (foreground)
    "Set up test infrastructure. Write unit tests for runtime/ and
     connectors/gmail/. Set up VCR fixtures."

  Step 6: Launch reviewer (foreground)
    "Review all Phase 0 code. Check import boundaries, type safety,
     spec generation, error handling."
```

**Phase 1 — Serve layer + more connectors:**
```
  Step 1: Launch serve-builder (foreground)
    "Build serve/mcp.py, serve/schema.py, serve/cli.py"

  Step 2 (parallel): Launch 2 connector-implementer agents
    Agent A: "Build Slack connector" (background)
    Agent B: "Build GitHub connector" (background)

  Step 3: Launch test-engineer (foreground)
    "Build conformance test framework. Add tests for Slack + GitHub."

  Step 4: Launch reviewer → verify Phase 1
```

**Phase 2 — Protocol diversity (heavy parallelism):**
```
  Step 1: Launch principal-architect
    "Build GraphQL protocol adapter in runtime/protocol/graphql.py"

  Step 2 (parallel): Launch 4 connector-implementer agents
    Agent A: "Build Notion connector" (background)
    Agent B: "Build Jira connector" (background)
    Agent C: "Build Google Drive connector" (background)
    Agent D: "Build Google Calendar connector" (background)

  Step 3: Launch connector-implementer
    "Build Shopify or Linear connector using GraphQL adapter"

  Step 4: Launch reviewer → verify Phase 2
```

### 11.7 Agent Army Orchestrator (Claude Agent SDK)

The orchestrator is a **Python application** that autonomously manages the entire agent team. You brainstorm → update the task board → run the orchestrator → it builds everything.

#### Architecture

```
.agents/
├── orchestrator/                    # The autonomous engine
│   ├── __init__.py
│   ├── main.py                      # Entry: python -m agents.orchestrator run
│   ├── engine.py                    # DAG executor — topological sort, parallel dispatch
│   ├── runner.py                    # Agent session manager — spawns Claude via API
│   ├── taskboard.py                 # Task board reader/writer
│   ├── state.py                     # Persistent state (SQLite) — tracks progress
│   ├── reporter.py                  # Completion notifications (terminal, file, webhook)
│   ├── config.py                    # Orchestrator config (API keys, concurrency, model)
│   │
│   ├── tools/                       # Tool definitions given to each agent
│   │   ├── __init__.py
│   │   ├── filesystem.py            # Read, write, edit, glob, grep files
│   │   ├── shell.py                 # Run bash commands (sandboxed)
│   │   ├── git.py                   # Git operations (commit, branch, diff)
│   │   ├── test.py                  # Run pytest, mypy, ruff
│   │   └── taskboard.py            # Update own task status, report blockers
│   │
│   └── prompts/                     # System prompt templates per agent type
│       ├── base.py                  # Shared context injected into all agents
│       ├── principal_architect.py
│       ├── connector_implementer.py
│       ├── serve_builder.py
│       ├── test_engineer.py
│       ├── health_watcher.py
│       ├── documenter.py
│       └── reviewer.py
│
├── skills/                          # Existing skill files (behavioral rules)
│   ├── principal_architect/SKILL.md
│   └── ...
│
├── taskboard.yaml                   # THE task queue — source of truth
├── state.db                         # SQLite — agent sessions, progress, logs
└── logs/                            # Per-session agent transcripts
    ├── 2026-04-04_build-spec-types.log
    └── ...
```

#### Task Board Format (taskboard.yaml)

```yaml
# .agents/taskboard.yaml — the source of truth for all work
version: "1.0"
project: toolsconnector
current_phase: 0

tasks:
  # --- Phase 0: Core Primitive ---
  - id: build-spec-types
    agent: principal-architect
    phase: 0
    priority: 1
    status: pending              # pending | running | completed | failed | blocked
    description: |
      Build the spec/ module with all specification types:
      - ConnectorSpec, ActionSpec, AuthSpec, PaginationSpec, ErrorSpec
      - All Pydantic V2 models with JSON Schema generation
      - ConnectorCategory and ProtocolType enums
      - Spec version constant
    files:
      - toolsconnector/spec/__init__.py
      - toolsconnector/spec/connector.py
      - toolsconnector/spec/action.py
      - toolsconnector/spec/auth.py
      - toolsconnector/spec/types.py
      - toolsconnector/spec/pagination.py
      - toolsconnector/spec/errors.py
      - toolsconnector/spec/version.py
    dependencies: []
    acceptance:
      - "All spec types have model_json_schema() working"
      - "mypy passes with --strict"
      - "Unit tests exist for all models"

  - id: build-error-hierarchy
    agent: principal-architect
    phase: 0
    priority: 2
    status: pending
    description: |
      Build the errors/ module with the full error hierarchy:
      ToolsConnectorError → AuthError, APIError, TransportError, ConnectorError, ConfigError
      Each error has: connector, action, code, message, retry_eligible, suggestion, details
      Both to_dict() and __str__() rendering.
    files:
      - toolsconnector/errors/__init__.py
      - toolsconnector/errors/base.py
      - toolsconnector/errors/auth.py
      - toolsconnector/errors/api.py
      - toolsconnector/errors/transport.py
      - toolsconnector/errors/config.py
      - toolsconnector/errors/codes.py
    dependencies: [build-spec-types]
    acceptance:
      - "All error types are catchable Python exceptions"
      - "error.to_dict() produces valid JSON"
      - "error.suggestion is populated for retryable errors"

  - id: build-types-module
    agent: principal-architect
    phase: 0
    priority: 2
    status: pending
    description: |
      Build types/ module: PaginatedList[T], FileRef, CredentialSet, OAuthConfig
    files:
      - toolsconnector/types/__init__.py
      - toolsconnector/types/paginated.py
      - toolsconnector/types/file.py
      - toolsconnector/types/credentials.py
    dependencies: [build-spec-types]

  - id: build-keystore
    agent: principal-architect
    phase: 0
    priority: 3
    status: pending
    description: |
      Build keystore/ module: KeyStore protocol, InMemoryKeyStore, EnvironmentKeyStore
    files:
      - toolsconnector/keystore/__init__.py
      - toolsconnector/keystore/base.py
      - toolsconnector/keystore/memory.py
      - toolsconnector/keystore/env.py
    dependencies: [build-spec-types]

  - id: build-runtime-core
    agent: principal-architect
    phase: 0
    priority: 4
    status: pending
    description: |
      Build the runtime engine:
      - Transport layer (httpx-based)
      - Auth provider system (AuthProvider protocol + API key + OAuth2 + Bearer)
      - Protocol adapter layer (ProtocolAdapter protocol + RESTAdapter)
      - Middleware pipeline (Middleware protocol + auth + retry + rate_limit + logging)
      - Pagination strategies (cursor, token, offset, page_number, link_header)
      - Serialization layer (JSON, XML)
      - BaseConnector abstract class
      - @action decorator with full introspection + sync/async bridge
      - run_sync() utility
    files:
      - toolsconnector/runtime/**/*.py
    dependencies: [build-spec-types, build-error-hierarchy, build-types-module, build-keystore]
    acceptance:
      - "BaseConnector can be subclassed"
      - "@action decorator generates ActionMeta with valid JSON Schema"
      - "Sync/async bridge works (sync call wraps async)"
      - "Middleware pipeline executes in correct order"
      - "RESTAdapter makes HTTP calls via httpx"
      - "Auth token refresh works transparently"

  - id: build-gmail-connector
    agent: connector-implementer
    phase: 0
    priority: 5
    status: pending
    description: |
      Build the Gmail connector as the first reference connector.
      Actions: list_emails, get_email, send_email, search_emails, list_labels,
               create_draft, delete_email, modify_labels, get_attachment
      Use RESTAdapter. Use Google API Python client as SDK.
      Full types in types.py (Email, Label, Attachment, Draft, etc.)
      Declare OAuth2 + ServiceAccount auth providers.
      Declare TokenPagination strategy for list actions.
    files:
      - toolsconnector/connectors/gmail/__init__.py
      - toolsconnector/connectors/gmail/connector.py
      - toolsconnector/connectors/gmail/types.py
    dependencies: [build-runtime-core]
    acceptance:
      - "gmail.list_emails() works with mocked HTTP"
      - "Gmail.get_spec() returns valid ConnectorSpec"
      - "All actions have @action decorator"
      - "All types are Pydantic V2 models"

  - id: build-tests-phase0
    agent: test-engineer
    phase: 0
    priority: 6
    status: pending
    description: |
      Build test infrastructure and write tests for all Phase 0 code.
      - pytest + pytest-asyncio + respx setup
      - Unit tests for spec/, errors/, types/, keystore/, runtime/
      - Unit tests for gmail connector (mocked HTTP)
      - Import boundary tests
      - Conformance test framework skeleton
    files:
      - tests/**/*.py
      - pyproject.toml (test dependencies)
    dependencies: [build-gmail-connector]

  - id: review-phase0
    agent: reviewer
    phase: 0
    priority: 7
    status: pending
    description: |
      Full review of all Phase 0 code. Check:
      - Import boundaries (spec/ → nothing, runtime/ → spec/ only, etc.)
      - Type safety (no Any, all hints present)
      - Docstrings (Google style, Args/Returns/Raises)
      - Error handling (framework errors used correctly)
      - Spec generation (every connector produces valid ConnectorSpec)
      - Test coverage (90%+ on runtime/)
      - Lines < 100 chars, files < 500 lines
    dependencies: [build-tests-phase0]
```

#### DAG Executor (engine.py)

The executor reads the task board, builds a dependency DAG, and executes tasks in topological order with maximum parallelism:

```python
# Pseudocode for the DAG executor

class DAGExecutor:
    """Executes tasks respecting dependencies, with max parallelism."""

    def __init__(self, taskboard: TaskBoard, runner: AgentRunner, max_parallel: int = 4):
        self.taskboard = taskboard
        self.runner = runner
        self.max_parallel = max_parallel

    async def execute_phase(self, phase: int) -> PhaseResult:
        tasks = self.taskboard.get_tasks_for_phase(phase)
        dag = self._build_dag(tasks)

        while dag.has_pending():
            # Find all tasks whose dependencies are met
            ready = dag.get_ready_tasks()

            # Limit parallelism
            batch = ready[:self.max_parallel]

            # Launch agents in parallel
            results = await asyncio.gather(*[
                self._run_task(task) for task in batch
            ])

            # Update DAG with results
            for task, result in zip(batch, results):
                if result.success:
                    dag.mark_completed(task.id)
                    self.taskboard.update_status(task.id, "completed")
                else:
                    dag.mark_failed(task.id)
                    self.taskboard.update_status(task.id, "failed",
                                                  error=result.error)
                    # If a task fails, all dependent tasks are blocked
                    dag.block_dependents(task.id)

        return PhaseResult(
            completed=dag.completed_tasks,
            failed=dag.failed_tasks,
            blocked=dag.blocked_tasks,
        )

    async def _run_task(self, task: Task) -> TaskResult:
        """Spawn a Claude agent session for this task."""
        system_prompt = self._build_system_prompt(task)
        tools = self._get_tools_for_agent(task.agent)

        return await self.runner.run(
            system_prompt=system_prompt,
            task_prompt=task.description,
            tools=tools,
            working_dir=self.project_root,
            timeout=task.timeout or 3600,  # 1 hour default
        )
```

#### Agent Runner (runner.py)

Each agent is a Claude API conversation with tools:

```python
class AgentRunner:
    """Spawns Claude agent sessions via Anthropic API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    async def run(
        self,
        system_prompt: str,
        task_prompt: str,
        tools: list[Tool],
        working_dir: str,
        timeout: int = 3600,
    ) -> TaskResult:
        """Run an agent session to completion.

        The agent loop:
        1. Send task to Claude with system prompt + tools
        2. Claude responds with tool calls or text
        3. Execute tool calls (file ops, shell, git)
        4. Feed results back to Claude
        5. Repeat until Claude says "task complete" or timeout
        """
        messages = [{"role": "user", "content": task_prompt}]

        while not self._is_complete(messages) and not self._timed_out(timeout):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=system_prompt,
                tools=[t.to_anthropic_schema() for t in tools],
                messages=messages,
            )

            # Process response
            if response.stop_reason == "tool_use":
                tool_results = await self._execute_tools(response, tools, working_dir)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            elif response.stop_reason == "end_turn":
                return TaskResult(success=True, output=response.content)

        return TaskResult(success=False, error="timeout")
```

#### System Prompt Construction

Each agent gets a composite system prompt:

```python
def _build_system_prompt(self, task: Task) -> str:
    """Build system prompt for an agent."""

    # 1. Base context (same for all agents)
    base = self._read_file("agents/orchestrator/prompts/base.py")
    # Includes: project vision, architecture rules, coding standards

    # 2. Agent-specific persona (from SKILL.md)
    skill = self._read_file(f"agents/skills/{task.agent}/SKILL.md")

    # 3. Architecture plan (relevant section)
    plan_section = self._extract_plan_section(task.phase)

    # 4. Current project state
    project_state = f"""
    Current files: {self._list_project_files()}
    Recent git log: {self._git_log(5)}
    """

    # 5. Task-specific context
    task_context = f"""
    YOUR TASK: {task.description}

    FILES TO CREATE/MODIFY: {task.files}

    ACCEPTANCE CRITERIA:
    {task.acceptance}

    DEPENDENCIES COMPLETED: {task.dependencies}
    """

    return f"{base}\n\n{skill}\n\n{plan_section}\n\n{project_state}\n\n{task_context}"
```

#### Tools Given to Agents

Each agent gets sandboxed file system and shell access:

```python
AGENT_TOOLS = [
    # File operations
    Tool("read_file", "Read file contents", params={"path": str}),
    Tool("write_file", "Write/create file", params={"path": str, "content": str}),
    Tool("edit_file", "Edit file with search/replace", params={"path": str, "old": str, "new": str}),
    Tool("list_files", "List files matching glob", params={"pattern": str}),
    Tool("search_files", "Search file contents", params={"pattern": str, "path": str}),

    # Shell (sandboxed to project directory)
    Tool("run_command", "Run shell command", params={"command": str}),

    # Git
    Tool("git_status", "Show git status"),
    Tool("git_diff", "Show changes"),
    Tool("git_commit", "Commit changes", params={"message": str}),
    Tool("git_branch", "Create/switch branch", params={"name": str}),

    # Testing
    Tool("run_tests", "Run pytest", params={"path": str}),
    Tool("run_typecheck", "Run mypy", params={"path": str}),
    Tool("run_lint", "Run ruff", params={"path": str}),

    # Task management
    Tool("mark_complete", "Mark current task as complete"),
    Tool("report_blocker", "Report a blocker", params={"description": str}),
    Tool("request_review", "Request review of completed work"),
]
```

#### Running the Orchestrator

```bash
# User's workflow:

# 1. Edit the task board (or let Claude help brainstorm)
vim .agents/taskboard.yaml

# 2. Run the orchestrator
python -m agents.orchestrator run --phase 0

# Output:
# [14:00:01] Phase 0 starting (7 tasks, max 4 parallel)
# [14:00:02] ▶ build-spec-types      → principal-architect (starting...)
# [14:05:30] ✓ build-spec-types      → completed (5m28s)
# [14:05:31] ▶ build-error-hierarchy  → principal-architect (starting...)
# [14:05:31] ▶ build-types-module     → principal-architect (starting...)
# [14:05:31] ▶ build-keystore         → principal-architect (starting...)
# [14:12:15] ✓ build-error-hierarchy  → completed (6m44s)
# [14:10:03] ✓ build-types-module     → completed (4m32s)
# [14:08:45] ✓ build-keystore         → completed (3m14s)
# [14:12:16] ▶ build-runtime-core     → principal-architect (starting...)
# [14:35:22] ✓ build-runtime-core     → completed (23m06s)
# [14:35:23] ▶ build-gmail-connector  → connector-implementer (starting...)
# [14:50:11] ✓ build-gmail-connector  → completed (14m48s)
# [14:50:12] ▶ build-tests-phase0     → test-engineer (starting...)
# [15:05:30] ✓ build-tests-phase0     → completed (15m18s)
# [15:05:31] ▶ review-phase0          → reviewer (starting...)
# [15:15:45] ✓ review-phase0          → completed (10m14s)
#
# Phase 0 COMPLETE (7/7 tasks, 1h15m total)
# Branch: phase-0-core-primitive (ready for review)

# 3. Review the branch
git log phase-0-core-primitive --oneline
git diff main..phase-0-core-primitive --stat

# 4. Approve and merge
git merge phase-0-core-primitive
```

#### Configuration

```yaml
# .agents/orchestrator/config.yaml
orchestrator:
  api_key_env: ANTHROPIC_API_KEY
  model: claude-sonnet-4-6          # Sonnet for most tasks (fast + capable)
  model_overrides:
    principal-architect: claude-opus-4-6  # Opus for architecture decisions
    reviewer: claude-opus-4-6             # Opus for thorough review
  max_parallel: 4                    # Max concurrent agent sessions
  default_timeout: 3600              # 1 hour per task
  working_branch_prefix: "agent/"    # Git branch prefix
  log_dir: ".agents/logs"
  state_db: ".agents/state.db"

  # Safety
  sandbox:
    allowed_dirs: ["toolsconnector/", "tests/", "pyproject.toml"]
    blocked_commands: ["rm -rf", "git push", "pip install --user"]
    require_git_branch: true         # Agents MUST work on branches, never main
```

#### Cost Management

```
Estimated cost per phase (Claude Sonnet):
├── Phase 0 (7 tasks, ~75 min agent time): ~$5-15
├── Phase 1 (6 tasks, ~60 min): ~$4-12
├── Phase 2 (9 tasks, ~90 min): ~$6-18
├── Phase 3 (8 tasks, ~80 min): ~$5-15
└── Phase 4 (10 tasks, ~100 min): ~$7-20

Total Phases 0-4: ~$30-80 estimated

Using Opus for architect + reviewer: ~2x for those tasks
```

### 11.8 Agent Memory & Continuity

Each agent session should:
1. **Start** by reading the plan file and relevant skill file
2. **Use codevira** tools for session context if available (`get_session_context`, `get_roadmap`)
3. **Log decisions** via `write_session_log` at session end
4. **Update graph** via `update_node` for files changed

Cross-session continuity is maintained via:
- The plan file (this document) — source of truth for what to build
- `.agents/skills/` — behavioral rules for each agent type
- Codevira roadmap — tracks phase progress
- Git history — what was actually built
- Memory files — project context and decisions

### 11.8 Scaling the Agent Army (1000+ Connectors)

When scaling to 1000+ connectors, the agent team model enables:

1. **Batch connector implementation**: Launch 10 connector-implementer agents in parallel across worktrees, each building a different connector
2. **Automated quality gate**: Every connector PR triggers conformance tests automatically
3. **Health Agent at scale**: One health-watcher agent per connector category, monitoring upstream changes
4. **Community contributions**: External contributors follow the same connector-implementer rules; AI reviewer agent validates their PRs

```
For 1000 connectors:
├── Tier 1 (20): Core team builds, weekly health monitoring
├── Tier 2 (80): Core team builds, monthly health monitoring
├── Tier 3 (200): Community builds, AI-reviewed PRs, quarterly health
├── Tier 4 (700+): Auto-generated from OpenAPI specs, community-maintained
```

---

## Summary: What Makes This Foundation-Grade

| Foundation Requirement | How We Address It |
|---|---|
| Formal specification | `spec/` module + auto-extracted JSON Schema + standalone SPEC.md |
| Multi-language support | Spec-first design, conformance tests, codegen pipeline |
| Conformance testing | Language-agnostic JSON test fixtures |
| Governance | RFC process, BDFL → steering committee progression |
| Security | SECURITY.md, threat model, signed releases, SBOM, pip-audit |
| 1000+ tools | Protocol adapter layer handles REST/GraphQL/SOAP/gRPC/WS |
| Diverse auth | Pluggable AuthProvider system with 11+ implementations |
| Diverse pagination | PaginationStrategy pattern with 6+ implementations |
| Quality at scale | Conformance tests + AI-assisted review + Health Agent |
| Backward compatibility | SemVer, deprecation policy, RFC for breaking changes |
| Community contribution | Low barrier (single PR), clear docs, automated quality gates |
| Automated engineering | 7-agent team via Claude Agent SDK orchestrator |
| Fully autonomous execution | DAG executor, parallel dispatch, auto-retry, state persistence |
| Scale to 1000+ connectors | Batch agent parallelism, tiered quality, auto-generation |
| Cost efficient | ~$30-80 for full Phases 0-4, Sonnet for tasks, Opus for architecture |
