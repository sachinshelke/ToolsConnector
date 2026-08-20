# ToolsConnector — Architecture FAQ & Decision Record

> These are final architectural decisions made during the initial build.
> Each includes the reasoning and trade-offs so future contributors
> understand *why*, not just *what*.

---

## 1. Why `src/toolsconnector/` and not bare `src/` or flat `toolsconnector/`?

**Decision:** Use `src/toolsconnector/` (PyPA src-layout).

**Why:**
- `pip install toolsconnector` needs a Python package named `toolsconnector`. That means a directory with `__init__.py` named exactly `toolsconnector/`. This is non-negotiable — Python's import system requires it.
- The `src/` wrapper prevents a dangerous dev trap: without it, `import toolsconnector` in tests picks up the local directory instead of the installed package, hiding packaging bugs that only appear in production.
- This is the standard used by Pydantic, FastAPI, OpenTelemetry, and every CNCF/Linux Foundation Python project.

**What we rejected:**
- **Bare `src/`** (putting `spec/`, `runtime/` directly in `src/`): Imports would be `from spec import ConnectorSpec` — collides with any other package named "spec" and can't be pip-installed under the `toolsconnector` namespace.
- **Flat layout** (`toolsconnector/` at repo root): Works but fails the "accidental local import" test. Fine for small projects, wrong for a Foundation-grade library.

```
ToolsConnector/                    # Git repo root
├── src/
│   └── toolsconnector/            # The Python package
│       ├── __init__.py
│       ├── spec/
│       ├── runtime/
│       ├── connectors/
│       └── ...
├── tests/
├── .agents/
└── pyproject.toml
```

---

## 2. Why raw httpx instead of wrapping official SDKs?

**Decision:** Use raw `httpx` for most connectors. Use official SDKs only where the protocol is genuinely complex (Google APIs, AWS S3).

**Why raw httpx wins for simple REST APIs:**

1. **Consistency:** Every connector follows the same pattern — `_request()` helper, `httpx.AsyncClient`, JSON parsing. With SDKs, every connector is different (Slack SDK returns dicts, PyGithub returns objects, Jira SDK raises different exceptions).

2. **Dependency weight:** 20 SDK dependencies = 20 potential version conflicts, 200MB+ of transitive dependencies. httpx is 1 dependency that handles everything.

3. **Maintenance:** When Slack SDK v4 ships, we'd need to rewrite our wrapper. With raw httpx, a Slack API change is a URL path or field name update — surgical, not architectural.

4. **Control:** SDKs often don't expose pagination tokens, rate limit headers, or retry-after values. We need these for our middleware pipeline. Raw httpx gives us full control.

5. **"Wrapper of wrappers" anti-pattern:** The brainstorm explicitly warned against this. If we wrap `slack-sdk`, we're a wrapper around a wrapper around HTTP. Users ask "why not just use slack-sdk directly?" and we have no good answer.

**Where SDKs are justified (complex protocols):**

| Tool | Why | Package |
|---|---|---|
| Google (Gmail, Drive, Calendar) | Service accounts need JWT signing + key file parsing. Discovery documents change endpoint URLs. OAuth token exchange has Google-specific quirks. | `google-api-python-client` |
| AWS S3 | SigV4 request signing is 100+ lines of HMAC-SHA256 crypto that must be exactly right for security. XML response parsing. Multipart upload protocol. | `boto3` |

**Where raw httpx is the right call (16 connectors):**
- Slack, Discord, GitHub, GitLab, Notion, Jira, Linear, Asana, HubSpot, Salesforce, Stripe, Twilio, SendGrid, Outlook, Teams, Confluence

All of these are: Bearer token + JSON REST + one pagination pattern. Our httpx code handles this in ~400 lines per connector with full type safety.

**The practical test:** If the SDK adds value beyond "saves you from writing an HTTP call", use it. If the SDK is just `requests.get()` with a class wrapper, skip it.

---

## 3. Why Pydantic V2 and not dataclasses or TypedDict?

**Decision:** Pydantic V2 for all data models.

**Why:**
- `.model_json_schema()` generates JSON Schema — this single method powers the entire serve layer (MCP, OpenAI, Anthropic, Gemini schema generation). With dataclasses, we'd need a separate schema generation library.
- Input validation is built-in — connector inputs are validated before hitting APIs. Catches bugs at the boundary.
- Serialization via `.model_dump()` / `.model_dump_json()` — no manual dict-building.
- V2 has a Rust core — fast enough that it's not a bottleneck.
- It's already in our core dependencies (we can't avoid it for the spec types).

**What we rejected:**
- **dataclasses:** No validation, no JSON Schema generation, no serialization. We'd need 3 additional libraries to get what Pydantic gives us for free.
- **TypedDict:** No validation, no methods, can't inherit. Good for function signatures, wrong for domain models.
- **attrs:** Excellent library but less ecosystem support for JSON Schema generation.

---

## 4. Why async-native with sync wrappers?

**Decision:** All connector methods are `async def`. The `@action` decorator auto-generates synchronous wrappers.

**Why:**
- Modern Python (3.9+) has mature async support. AI agent frameworks (LangChain, CrewAI) are increasingly async.
- Writing async code and generating sync wrappers is easy (`asyncio.run()` or background thread). Writing sync code and making it async is impossible without rewriting.
- One implementation, two entry points, zero code duplication.

**How it works:**
```python
# Connector author writes ONE async method:
@action("List emails")
async def list_emails(self, query: str = "is:unread") -> PaginatedList[Email]:
    ...

# Users get both:
emails = gmail.list_emails(query="is:unread")         # sync (auto-generated)
emails = await gmail.alist_emails(query="is:unread")   # async (original, prefixed 'a')
```

**Edge case handling:**
- No event loop running → `asyncio.run()`
- Event loop already running (Jupyter, FastAPI) → dispatch to background thread via `run_coroutine_threadsafe()`

---

## 5. Why Protocol (structural typing) instead of ABC (nominal typing)?

**Decision:** `KeyStore`, `AuthProvider`, `PaginationStrategy`, `ProtocolAdapter`, `StorageBackend`, and `Middleware` are all `Protocol` classes, not ABCs.

**Why:**
- Duck typing is Pythonic. If your class has `get()`, `set()`, `delete()`, `exists()` — it IS a KeyStore. No need to inherit from our base class.
- External library classes can satisfy our protocols without modification. A Redis client that happens to have `get/set/delete/exists` methods works as a KeyStore without wrapping.
- Protocols are checked at type-check time (mypy) but don't constrain runtime. ABCs raise errors at import time if you forget a method.
- `@runtime_checkable` still allows `isinstance()` checks when needed.

**When ABC is justified:**
- `BaseConnector` is an ABC because connector authors MUST inherit from it — it provides the `@action` registration machinery, `get_spec()`, and lifecycle management. This is implementation inheritance, not interface specification.

---

## 6. Why a Protocol Adapter layer between connectors and HTTP?

**Decision:** Connectors don't call httpx directly. They go through a `ProtocolAdapter` (REST, GraphQL, SOAP, etc.).

**Why:**
- Most connectors today are REST, but the market has GraphQL (Shopify, Linear, GitHub), SOAP (SAP, banking), gRPC (Google Cloud), and WebSocket (Slack RTM, Discord Gateway).
- Without this layer, adding a GraphQL connector means mixing HTTP call logic with query building in the connector code.
- With the adapter layer, a GraphQL connector says `await self.adapter.request(query, variables=vars)` — same clean pattern as REST.

**Current state:**
- `RESTAdapter` — fully implemented, used by 18/20 connectors
- `GraphQLAdapter` — Linear uses raw httpx POST to /graphql (to be migrated)
- `SOAPAdapter`, `GRPCAdapter` — reserved for Phase 5 (enterprise connectors)

---

## 7. Why separate `spec/` from `runtime/`?

**Decision:** `spec/` contains pure Pydantic type definitions (the "what"). `runtime/` contains execution logic (the "how").

**Why — multi-language support:**
- When we build TypeScript/Go/Java SDKs, they need to implement the same interface contract. That contract is defined by `spec/` — pure types with JSON Schema generation.
- The TypeScript SDK imports `ConnectorSpec.schema.json` (extracted from Python's `spec/` module) and implements its own runtime.
- If spec and runtime were mixed, extracting the language-agnostic contract would require parsing Python implementation code.

**Import boundaries:**
```
spec/    → imports NOTHING from toolsconnector
runtime/ → imports spec/ (reads the contract it implements)
connectors/ → imports runtime/ + spec/ (uses the engine)
serve/   → imports spec/ only (reads metadata, never connector code)
```

> **Refinement (2026-05):** `spec/` today captures the *interface* (names, types, JSON Schema) but not the HTTP *binding* a generated runtime needs to actually make a call. FAQ #17 specifies the binding layer that completes this contract.

---

## 8. Why not build a dashboard, auth server, or hosted service?

**Decision:** ToolsConnector is a library. Period.

**Why (the "Primitive, Not Platform" principle):**
- The moment we add a dashboard, we need auth for the dashboard. Then we need user management. Then multi-tenancy. Then billing. Then we're Composio.
- Primitives win by doing one thing perfectly. HTTP doesn't have a dashboard. Docker doesn't manage your CI/CD. Redis doesn't build your cache strategy.
- Companies that want dashboards/auth/hosting build them ON TOP of our primitive. That's the Kafka model — Confluent built a business on Kafka's open-source core.

**What we provide instead:**
- Standard Python `logging` — pipe it to wherever you want
- `ConnectorSpec.model_json_schema()` — build any UI/dashboard from our schema
- Pluggable `KeyStore` — store credentials however you want
- Pluggable `Middleware` — add observability, cost tracking, approval flows

---

## 9. Why BYOK (Bring Your Own Key) and not managed auth?

**Decision:** Developers register their own OAuth apps, get their own API keys, handle their own consent screens. We handle the protocol (token exchange, refresh, scope validation).

**Why:**
- If we manage auth, we need a server. If we need a server, we're not a library anymore. (See FAQ #8.)
- BYOK means zero liability for credential storage. The developer owns their keys and chooses how to store them (our pluggable KeyStore helps, but it's their choice).
- Enterprise customers REQUIRE owning their credentials. They'll never send API keys to a third-party service.
- Most tools have free developer tiers. Getting an API key takes 5 minutes. We don't need to "manage" this.

**What we DO handle:**
- Token exchange (authorization code → access token)
- Token refresh (automatic, transparent, with `asyncio.Lock` for thread safety)
- Scope validation (know what permissions each action needs)
- Protocol quirks (each OAuth provider is slightly different)

---

## 10. Why Apache 2.0 license?

**Decision:** Apache 2.0.

**Why:**
- **Patent grant:** Apache 2.0 includes an explicit patent license. If we (or a contributor) hold patents on the code, users are automatically granted a license. MIT doesn't provide this.
- **Enterprise adoption:** Legal teams at large companies prefer Apache 2.0 because of the patent clause. MIT requires additional patent review.
- **Kafka model alignment:** Apache Kafka uses Apache 2.0. So do Kubernetes, TensorFlow, and most Foundation-grade projects.

**What we rejected:**
- **MIT:** Simpler but no patent protection. Fine for small libraries, risky for a primitive that enterprises will embed deeply.
- **LGPL/GPL:** Copyleft restrictions scare enterprises away. Kills adoption.
- **BSL/SSPL:** "Open source but not really" licenses that fragment the community.

---

## 11. Why 20 connectors at launch, not 5 or 500?

**Decision:** Launch with 20 real connectors across 8+ categories.

**Why:**
- **5 is too few:** Doesn't prove the architecture handles diversity. "Works for Gmail and Slack" isn't convincing. We need CRM, project management, finance, storage, and code platforms to show universality.
- **500 is too many:** Quality drops. Maintenance burden explodes. The Health Agent doesn't exist yet to automate updates.
- **20 hits the sweet spot:** Covers every major category, proves all pagination/auth/protocol patterns work, gives enough critical mass for adoption.

**The practical reality (from the brainstorm):**
> "Nobody is going to use 1000+ tools. People will configure 5 to 6 or 10 to 20 as per their need."

20 connectors means any real deployment can be fully served from day one.

---

## 12. How should new connectors decide: SDK vs raw httpx?

**Decision framework:**

```
Is the auth protocol complex (SigV4, JWT signing, service accounts)?
├── YES → Use SDK (e.g., boto3 for AWS, google-api-python-client for Google)
└── NO
    ├── Is the data format non-JSON (XML, protobuf, SOAP)?
    │   ├── YES → Use SDK or specialized parser
    │   └── NO → Raw httpx
    └── Is the API well-documented with stable REST endpoints?
        ├── YES → Raw httpx (our standard pattern)
        └── NO → Consider SDK for discovery/documentation
```

**Rule of thumb:** If you can implement the connector in <500 lines of httpx code with full type safety, don't add an SDK dependency. The consistency of our patterns outweighs the convenience of the SDK.

---

## 13. Why the Agent Army Orchestrator instead of manual development?

**Decision:** Build an autonomous agent orchestrator that reads a task board and dispatches Claude agents to build code.

**Why:**
- **Scale:** 20 connectors × 8 actions × types + tests = thousands of lines. Manual coding is slow.
- **Consistency:** Agents follow the same prompt/persona every time. A human developer drifts after the 5th connector.
- **Parallelism:** 4 agents building 4 connectors simultaneously. One human can't parallelize.
- **Reproducibility:** Re-run the orchestrator and get the same output. Human memory fades.

**When to NOT use the orchestrator:**
- Architecture decisions (needs human judgment)
- Security-critical code (auth, crypto — needs careful review)
- Novel patterns (first-of-a-kind implementations)
- Bug fixes (too narrow for a full agent session)

---

## 14. What's the versioning strategy?

**Decision:** Semantic versioning (SemVer) with spec-aligned major.minor.

```
Spec version:    1.0, 1.1, 1.2, 2.0
Python SDK:      1.0.0, 1.0.1, 1.1.0, 1.1.1, 2.0.0
TypeScript SDK:  1.0.0, 1.0.1, 1.1.0
```

- **Major:** Breaking changes to spec or public API
- **Minor:** New connectors, new actions, new auth providers (additive)
- **Patch:** Bug fixes, documentation, internal improvements

**Deprecation policy:**
- Deprecated features are marked with `deprecated=True` in ActionSpec
- Deprecated features work for at least 1 minor version
- Removed in the next major version

---

## 15. What's the minimum Python version and why?

**Decision:** Python 3.9+

**Why:**
- 3.9 introduced `dict[str, Any]` and `list[str]` syntax (no more `Dict`, `List` imports needed)
- 3.8 reached EOL in October 2024 — no security patches
- 3.9 is the oldest version still receiving security updates (until October 2025)
- Pydantic V2 requires 3.8+ but performs best on 3.9+
- We use `from __future__ import annotations` for forward-compatible type hint syntax

**What we can't use (requires 3.10+):**
- `match` statements (structural pattern matching)
- `X | Y` union syntax at runtime in Pydantic fields (we use `Optional[X]` instead)
- `ParamSpec` for advanced decorator typing

---

## 16. Why a verification-tier system (live / doc / pattern)?

**Decision:** Every connector carries a `verification_status: ClassVar[str]` — one of `"live"`, `"doc"`, or `"pattern"` — that propagates through `ConnectorSpec` into `site/data.json` and renders as a color-coded badge on the catalog site.

| Tier | Value | Criteria |
|---|---|---|
| **Tier 1 — Live verified** | `"live"` | Doc-verified AND exercised end-to-end against the real vendor API with a real token |
| **Tier 2 — Doc verified** | `"doc"` | Every endpoint / header / scope / body cross-checked against canonical vendor docs + respx-mocked |
| **Tier 3 — Pattern correct** | `"pattern"` | Code matches documented API patterns from public knowledge, but no active doc or live verification has happened |

**Why:**
- **Honest quality claims.** "Verified" has to mean something specific. Shipping 74 connectors and calling them all equally trustworthy would be dishonest — most are pattern-correct, a handful are live-verified. The tier makes the difference legible instead of implied.
- **Agent-consumable.** The status is a string enum on the spec, so an agent can `kit.list_tools()[0]["verification_status"]` and filter for production-ready connectors at runtime — not just a human-facing docs note.
- **Drives the roadmap.** The progression Tier 3 → 2 → 1 is the unit of work for each connector-hardening pass. The CHANGELOG records which connectors moved tiers in each release.
- **Default is honest, not flattering.** New connectors inherit `"pattern"` — the *weakest* claim — so a connector can only earn a stronger tier by explicit promotion, never by omission.

**Why live verification matters (not just respx):** respx mocks assert the connector sends what *we think* the API wants — they can't catch a wrong assumption baked into both the connector and its mock. Live runs against the real API have surfaced bugs respx silently accepted: `gdocs.insert_text` awaiting a sync wrapper, `gdrive.upload_file`'s spurious `Content-Transfer-Encoding`, `gtasks.update_task_list` using PUT where Google demands PATCH. The `"live"` tier certifies that this class of bug was checked for, not just the request-shape. The payoff compounds beyond REST: `odoo` — the first JSON-RPC connector in the catalog (live-verified 2026-06-19 against a real Odoo 19.3 instance across ~27 apps / ~50 models) — proves the tier system is protocol-agnostic, not REST-specific.

**Why not a richer scheme (percentages, per-action flags)?** A 3-value enum is the smallest thing that captures the meaningful distinction (real API hit vs. docs only vs. neither). Per-action verification detail lives in each connector's README "Verification Status" table; the spec-level field stays coarse so it's cheap to query and render.

**Reference:** see `ROADMAP.md` → "Verification tiers" for the live registry of which connector sits where.

---

## 17. How will we ship native SDKs in other languages from one source of truth?

**Decision:** Generate native, in-process SDKs (TypeScript, Go, Java, Ruby, …) from **one declarative source of truth** by formalizing the existing connector IR into a **Smithy-style HTTP-binding layer** plus a small per-language **executor runtime**. We will **not** adopt an OpenAPI generator vendor, and we will **not** build a single Rust/WASM core with language bindings.

This extends FAQ #7: that entry established that the language-agnostic *contract* lives in `spec/`. This entry specifies the one thing the contract is currently missing — the **HTTP binding** a generated runtime needs to actually make the call.

**The gap (why we cannot generate other languages today):**
- `spec/` captures the **interface** — action names, parameter types, JSON Schema, danger flags, a pagination *enum*. That is enough to generate MCP / OpenAI / Anthropic function schemas and docs (which is why those already work).
- It captures **none of the HTTP binding** — method, path template, which argument is a path/query/header/body param, serialization style (`fields[0]=`, `sort[0][field]=`, `records[]=`), body wrapping/encoding (JSON vs form), per-action base URL, response unwrap, pagination plumbing. That logic lives only inside each connector's imperative `_request` / `@action` body.
- Corroborating signals in the tree: `runtime/serialization/` is an empty placeholder; `codegen/spec_extractor.py::generate_openapi()` emits `POST /api/v1/{connector}/{action}` — it models actions as RPC to the *ToolsConnector* server, not the real upstream. A vendor consuming that OpenAPI would generate clients of a TC service — the server-based shape we explicitly reject (FAQ #8).

**What we rejected:**

| Option | Who ships this way | Why not for us |
|---|---|---|
| **(a) OpenAPI + generator vendor** (Stainless, Speakeasy, Fern) | OpenAI, Anthropic, Cloudflare, Vercel | Generates an idiomatic client of **one** server-style API. Cannot natively model 68 *different* upstreams, 14-service SigV4, or per-connector custom pagination running **in-process**. Our value is the unified primitive, not one HTTP surface. |
| **(c) Rust / WASM core + bindings** (PyO3, napi-rs, UniFFI) | Mozilla (Firefox), some DB drivers | Right when there is heavy shared **compute**. We are thin HTTP wrappers — the cost is a Rust toolchain + per-language, per-platform native-binary fan-out. Betrays the **lightweight, in-process** identity. |
| **(b) Custom connector IR/IDL + multi-target generator (Smithy-style)** ✅ | AWS (Smithy → 12+ in-process SDKs with native SigV4) | We are **already a Smithy-shaped system**: declarative Pydantic IR in `spec/`, pluggable `runtime/{auth,pagination,protocol}` executors, a service-agnostic SigV4 signer (`connectors/_aws/signing.py`). The only missing piece is a bounded binding vocabulary — config, not code. |

**The binding layer we add (a finite, Smithy-shaped vocabulary):**
- **Param binding** — `location` (path/query/header/body), `wire` name, `style` (simple / indexed `[i]` / indexed-object `[i][k]` / bracket `[]` / form-explode / map `[k]`), bounded transforms (min/max clamp, max-items), body key + per-item wrap, **scalar value-wraps** (`rich_text` → `[{"text":{"content":x}}]`, `object` → `{k:x}`), and whole-body pass-through (`raw_body_param`).
- **Body** — encoding (json/form), optional single-key wrap (`{"product": …}`).
- **Endpoints** — named base URLs (multi-base: Airtable data/meta, Twilio main/verify), per-endpoint auth + default encoding; base/path templating from credential-derived context vars (`{store}`, `{account_sid}`).
- **Pagination** — offset-token / link-header / follow-URL, with token field + re-injection param + carry set.
- **Auth** — reuses the existing `AuthSpec` enum (Bearer / header-key / basic-from-split / SigV4 / HMAC); the signer is a per-language runtime lib, the spec just declares the trait (the Smithy model).

**Evidence — the de-risking spike (`experiments/sdk_spike/`):**
- Took the **3 hardest** connectors (Airtable, Twilio, Shopify — chosen because they combine the gnarliest patterns) and authored declarative bindings for 9 representative actions.
- A generic ~180-line **executor** + ~120-line **IR schema** reproduced the **exact** HTTP requests of the hand-written connectors — verified by driving the *real* connectors through `httpx.MockTransport` and asserting byte parity.
- **Result: 13/13 requests expressible declaratively, 0 escape hatches.** 21 distinct hard patterns covered.
- That ~300-line runtime drives what is **2,264 lines** of imperative connector code (for just those 3) → the leverage, and the "lightweight" requirement, are real. Bindings serialize to 1–2 KB of round-tripping JSON — a true language-agnostic artifact.
- **Bonus:** the executor was *more correct* than the hand-written code in 2 cases, surfacing latent production bugs (Shopify never substitutes `{store}`; Twilio pagination doubles the `/2010-04-01` path prefix). One audited executor eliminates a whole **class** of per-connector bugs.

**Escape hatch (the honest hard 20% — measured at 2.6%):** the design includes a per-action imperative override for the genuine minority that resist declarative expression (as Smithy and Stainless both do). The spike needed zero for the hardest 3, and the full-catalog measurement below puts the real ceiling at **2.6%**, not 20%.

**Measured coverage (2026-06-13 — resolves open question 1):** the AST classifier (`experiments/sdk_spike/coverage.py`) run across the full catalog of **73 connectors / 1,519 actions**:

| Class | Count | Share | Meaning |
|---|---|---|---|
| **DECLARATIVE** | 1,386 | **91.2%** | 1:1 `ActionBinding`, no imperative smell |
| REVIEW | 94 | 6.2% | soft smell only (manual query-string `.join`, composite/local-only helpers, response-header reads) — likely declarable with small vocab additions |
| **ESCAPE_HATCH** | 39 | **2.6%** | genuinely needs an imperative override |

Declaratively expressible: **91.2% hard floor, 97.4% with vocab additions**. The 39 escape-hatch actions fall into exactly two families:
- **23 × sequential-request orchestration** (e.g. `gmail.get_attachment`, `outlook.list_calendar_events`, `firestore.run_transaction`) — fetch-then-fetch flows that are irreducibly imperative; these are the permanent escape hatches.
- **16 × computed request material** (inline base64 / uuid / hashlib / hmac in the body, e.g. `gdrive.upload_file`, `webhook.send_with_hmac`, `route53.create_hosted_zone`) — absorbable later via a bounded `transform` vocab entry if the per-language duplication ever justifies it.

**Verdict: the gate passes.** A per-action override rate of 2.6% is comfortably below what Smithy-style systems carry; proceed to phase 1.

**Open questions (resolve before broad rollout):**
1. ~~**Full-scale coverage** — what is the real escape-hatch % across all actions?~~ **Resolved 2026-06-13: 2.6%** (measured above).
2. **Build vs. reuse** — keep our Pydantic IR + write per-language emitters, or transpile to **Smithy IDL** and reuse AWS's mature `smithy-{typescript,go,java}` generators (native SigV4 + paginators)? Smithy's generators are AWS-protocol-oriented and may not cleanly target arbitrary third-party REST/GraphQL.
3. **Per-language runtime cost** — even Smithy/Stainless hand-maintain a small runtime lib (signer, pagination, retry, errors) beneath generated code. "Build once" still means owning ~N thin runtimes; quantify it.
4. **MCP at 1,500+-action scale** — one-tool-per-action may stop being token-efficient; revisit a consolidated tool surface.

**Phased path:**
1. Make the binding the source of truth in **Python** (extract bindings from connectors; drive the Python runtime off them) — proves sufficiency at full scale, confirming the classifier's 2.6% escape-hatch prediction action-by-action.
2. **Decision gate** (build vs. reuse), then generate a native, in-process **TypeScript** SDK for the declarative actions.
3. Add a language = add a thin runtime + templates (Go next); joint CI publishing to npm / PyPI / crates.io / Maven.

**Phase 1 progress (2026-06-16):** the binding is now **load-bearing in Python** for **4 connectors / 146 actions** — Stripe (39/40), GitHub (36/37), Notion (21/24), Slack (50/51). Each connector's `@action` bodies build their requests through the shared `spec/executor.build_request`; the imperative copy of the wire shape is gone. Every migration is gated by a **byte-parity oracle** (drive the real connector through `httpx.MockTransport`, assert the binding reproduces the exact request) — 23/23 for Notion, 60/60 for Slack, folded into the connector test suites for Stripe/GitHub. Action-by-action this confirms the classifier: the only escape hatches encountered are genuinely value-conditional or non-JSON (Stripe `cancel_subscription` — HTTP method flips on an arg; GitHub `create_gist` — per-value file map; Notion `search` / `create_page` / `add_comment` — body shape branches on which arg is present; Slack `upload_file` — form/multipart, not JSON), **6/152 = 3.9%** — in line with the 2.6% catalog floor given these were chosen for difficulty/breadth. The migrations also grew the "bounded transform vocab" (line above) instead of multiplying hatches: Notion's `rich_text` / `object` scalar-wraps + `raw_body_param`, and Slack's lowercase-boolean query encoding + dotted pagination cursor (`response_metadata.next_cursor`) + existing `body_wrap` for the nested `{"profile": …}` status body. `ensure_ascii=False` in the executor's JSON encoder keeps non-ASCII bodies byte-identical to httpx.

**Generation seam closed (2026-06-17 — phases 2-3 realized):** the spike's prototype generators were promoted to production. `scripts/gen_sdks.py` reads the **same production bindings** that drive the Python runtime (`src/.../connectors/*/binding.py`) and emits typed clients straight into the shipped packages (`sdks/typescript/src/*.ts`, `sdks/go/*.go`) — the spike's `gen_{ts,go}.py` (which read `experiments/sdk_spike/specs.py`) are superseded. The TS + Go runtimes were ported to the full IR (wrap / raw_body_param / min / dotted-cursor / lowercase-query-bool). A connector bound in Python now flows to all three languages by re-running one script — **zero hand-written per-language connector code**. `scripts/sdk_parity.py <conn>` is the cross-language gate: it drives each connector's action matrix through Python `build_request`, TS `buildRequest` (Node type-strip), and Go `BuildRequest` (go test), comparing canonical method + host + path + sorted-query + parsed-body + auth. **All 4 connectors green: Stripe 39/39, GitHub 36/36, Notion 23/23, Slack 60/60 — 158 rows identical across Python · TypeScript · Go.** Go-specific reconciliations: connector-prefixed arg-struct types (flat package namespace), `raw_body_param` injected as a typed arg, `scalarStr` for lowercase query bools (Go's `str(bool)` is `"True"`), and parsed-body comparison (Go's `encoding/json` sorts map keys). Still open: npm-publish + go-tag release CI (batched).

**References:** FAQ #2 (raw httpx), #6 (Protocol Adapter), #7 (spec/ vs runtime/), #8 (primitive, not platform), #14 (versioning across language SDKs); spike write-up at `experiments/sdk_spike/README.md`.

## 18. Why CodeQL "advanced setup" (committed `codeql.yml`) instead of GitHub Default Setup?

**Decision:** Run code scanning via the **advanced workflow** (`.github/workflows/codeql.yml`) with the **`security-extended`** query suite across **three languages** (`python`, `javascript-typescript`, `actions`), and **SHA-pin all third-party GitHub Actions**. We disabled GitHub **Default Setup** to do this.

**Context — the two modes are mutually exclusive.** GitHub offers Default Setup (UI-managed, zero-config) and Advanced Setup (a workflow file you own). Enabling Default Setup *auto-disables* any committed `codeql.yml`. For a period this repo had **both registered** — Default Setup active on the narrower **`default`** suite, while the committed advanced `codeql.yml` sat `disabled_manually`. So the repo *shipped* a workflow claiming `security-extended` that **wasn't actually running**, and live coverage was shallower than intended.

**Why advanced wins for us:**

| Need | Default Setup | Advanced (`codeql.yml`) |
|---|---|---|
| Query depth | `default` suite only | **`security-extended`** (catches e.g. `actions/unpinned-tag`, more injection/sanitization sinks) |
| On-demand branch scan | ❌ push-to-main + PRs only | ✅ **`workflow_dispatch`** — scan any branch with no PR |
| Config in version control | ❌ UI state | ✅ reviewed in-repo, same as any code |
| Language set | implicit | **explicit matrix** — guarantees we don't silently drop a language |

**Trade-off (accepted):** `security-extended` + 3 languages surfaces *more* findings than Default Setup did, and we now own the workflow file (Dependabot keeps the pinned action SHAs current). We accept the small maintenance cost for deeper, on-demand, version-controlled scanning — consistent with the Foundation-grade bar.

**Action-pinning policy:** third-party actions are pinned to a **full commit SHA** (with the version as a trailing comment so Dependabot can bump them); first-party `actions/*` and `github/*` are left tag-pinned (GitHub-owned, not flagged by CodeQL). This closes the `actions/unpinned-tag` supply-chain class — a moved/hijacked tag can't silently change what runs in CI.

**Operational note:** when switching modes, disable Default Setup **before** enabling the advanced workflow (GitHub rejects an advanced run while Default Setup owns scanning). After the switch, `main` is re-scanned by the advanced workflow on its next push to `main`.

**References:** FAQ #8 (primitive, not platform — the scanner is CI-only, never ships), #14 (versioning); `SECURITY.md` (disclosure + design principles); `.github/workflows/codeql.yml`.

## 19. Why is LinkedIn several connectors (`linkedin`, `linkedin_leads`, …) instead of one — and why no "people search"?

LinkedIn is not one API; it's a portfolio of separately-gated products (member Share, Marketing/Lead Sync, Conversions, Community Management, Advertising), each with its **own credential, scope, approval gate, and verification tier**. We split connectors along that **credential/product boundary** — the same way Google is `gmail` / `gdrive` / `gcalendar` rather than one `google`.

**Why not one mega-connector with capability flags?** Two hard constraints make it impossible to do honestly:

1. **One credential per connector.** `ToolKit` takes a single `credentials` value per connector. But LinkedIn's surfaces need *different tokens obtained different ways* — a member OAuth token (`w_member_social`, self-serve), the Conversions **Direct API** token (a non-expiring token minted in Campaign Manager — not even OAuth), and marketing-scoped OAuth tokens behind LinkedIn's review. A single connector handed one token would 403 on most of its actions.
2. **One verification tier per connector.** `verification_status` is a single field (FAQ #16). `linkedin` is **live** (Tier 1); `linkedin_leads` is **doc** (Tier 2, pending product approval). A mega-connector could carry only one label — forcing it to over-claim "live" for unverified surfaces or under-claim "doc" for the live ones. The honesty rule needs **per-surface** tiers, hence per-surface connectors.

The rule of thumb: **the connector boundary is the credential, not the brand.** Same token → one connector with all those capabilities (so image/video/document *media* uploads live inside `linkedin`, not a separate connector — they ride the same `w_member_social` token as `create_post`). A different token/product/approval → a new connector.

**Why there is no people-search / profile-enrichment connector.** Users often ask for "search people by filters → return their email/phone," or "expand a person URN into their career history." **LinkedIn exposes no such API to BYOK developers, by design** — verified across the Profile API ("restricted to approved developers," plus a hard *storage ban* on non-authenticated members and per-app-opaque person IDs), the Connections API (partner-gated, authenticated user's 1st-degree only), and the Messages API (approved partners + a human-in-the-loop-per-message rule). The only way to fake it is scraping, which violates LinkedIn's User Agreement and data-protection law — and our charter (FAQ #8, #9) refuses to harvest third-party PII. Being authenticated as yourself does not authorize extracting *other people's* private data.

The **legitimate** "get people's contact details" path is `linkedin_leads` (the Lead Sync API): it returns leads — name/email/phone — that members *voluntarily submitted* to **your own** Lead Gen Forms. First-party, consented, opt-in. That is the boundary: we expose the full power the API actually offers, not capabilities the platform deliberately withholds.

**References:** FAQ #8 (primitive, not platform), #9 (BYOK), #16 (verification tiers); connector READMEs under `src/toolsconnector/connectors/linkedin*/`.

## 20. How does multi-tenant credential rotation work (`ToolKitFactory` + OAuth2 keystore keys)?

**The bug class this answers (gap analysis G3/G4, 2026-07-22):** a platform embedding ToolsConnector for *its* users (the B2B2C persona) refreshes a tenant's OAuth token, calls `for_tenant(tenant_id, new_credentials)` — and silently gets back a cached kit still holding the **old** token. Separately, `OAuth2Provider` persisted refreshed tokens under `{connector}:default:{field}` regardless of tenant, so two tenants refreshing the same connector overwrote each other in the keystore.

**Decisions:**

1. **Credentials are part of the cache identity.** `ToolKitFactory.for_tenant` compares the passed credentials against the ones the cached kit was built with (a defensive copy, so caller-side mutation can't mask a rotation). Same credentials → cached kit; different → the stale kit is *retired* (connector instances torn down) and a fresh kit is built. No `refresh=` flag to remember — rotation is detected, not declared, so the failure mode "platform forgot to pass the flag" cannot exist.
2. **Retirement never blocks the caller's event loop.** Inside a running loop, teardown is scheduled as a task (awaited at `close_all`); in sync contexts it completes via the `run_sync` bridge. `ToolKit.aclose` already swallows per-connector teardown errors, so retirement can't fail a request.
3. **Bounded cache is opt-in (`max_tenants=None` default), LRU on overflow.** Default stays unbounded because evicting a kit *closes* it, which would break callers that hold long-lived kit references — a silent behavior change for existing single-tenant users. Platforms with many tenants opt in and follow the documented discipline: re-fetch via `for_tenant` per request, `close_tenant` on disconnect, `close_all` on shutdown.
4. **`OAuth2Provider` takes `tenant_id` (default `"default"`)** and persists under the documented `{connector}:{tenant}:{type}` convention from `keystore/base.py`. Single-tenant callers keep their existing key namespace; multi-tenant refresh no longer collides.

**Deliberately not done here:** factory↔KeyStore integration (auto-loading per-tenant credentials from a keystore) — that belongs to the `toolsconnector.auth` wiring work (G1/G2, decision D00000F), where credential *sourcing* is designed as a whole rather than bolted onto the cache.

**References:** `serve/toolkit.py` (`ToolKitFactory`), `runtime/auth/oauth2.py`, `keystore/base.py` (key convention), `.agent/artifacts/whatsapp-connector-plan.md` §9a (G3/G4).

---

## 21. How do inbound events (webhooks) work if we're "a primitive, not a platform"?

**Decision: the library ships pure verify/parse primitives; the listener is always the developer's.** For `whatsapp_business` that is `verify_signature()`, `handle_verification()` and `parse_events()` — exported functions, not `@action`s, because receiving is not a request/response call.

**Why not ship a receiver?** FAQ #8 bans *us running a service*, not shipping a self-hosted surface (`serve/rest.py` and the MCP server are precedent). A hosted receiver would need retries, queues, replay stores and multi-tenant routing — each one a step from primitive to platform. A stateless `verify → parse → your callback` app can be added later as an optional extra; it must never become the only path.

**Why this matters more than it looks.** WhatsApp is push-only: there is *no* polling endpoint, Meta retries for up to 7 days, and anything missed beyond that is unrecoverable. So "receive" cannot be an action — it is an endpoint you own. What the library can do is make the hard parts safe:

- **Signature verification over raw bytes** with a constant-time compare. Re-serializing the JSON breaks the signature, so the helper takes `bytes`, and hostile header values return `False` instead of raising.
- **Typed event parsing** across the full taxonomy, with `waba_id` and `phone_number_id` lifted onto every event as routing keys — the thing a multi-tenant platform actually needs, since one Meta app receives events for all its customers.
- **Documented delivery reality**: dedupe by `wamid` (Meta re-sends — observed live), don't assume ordering, ACK 200 fast and process async.

**Credential asymmetry worth knowing:** signature verification uses the *app secret* (app-level, one per Meta app) while actions use the *tenant's* access token. Platforms verify once at the edge, then route by the event's WABA/phone id.

**Precedent for other connectors:** vendors with pull APIs keep using actions (`telegram.get_updates`, `stripe.list_events`, `gmail.list_history`). Shape A (primitives) is for push-only vendors; don't invent a polling action where the vendor has none.

**References:** `connectors/whatsapp_business/webhooks.py`, `examples/17_whatsapp_webhook_receiver.py` (runnable localhost receiver), `tests/connectors/test_whatsapp_webhook_integration.py`.

---

## 22. Why is there no personal-WhatsApp connector?

**Decision (locked): we ship `whatsapp_business` (the official Cloud API) and `whatsapp` (offline links). There is no personal-account transport, and there will not be one.**

Personal WhatsApp has **no official API**. Every "personal WhatsApp API" — Baileys, whatsmeow, whatsapp-web.js, WPPConnect, and the hosted services reselling them — reverse-engineers the linked-device protocol. That violates WhatsApp's Terms of Service, including a clause aimed squarely at libraries like ours: *create software or APIs that function substantially the same as our Services and offer them for use by third parties*. Enforcement is active (warning banners since May 2025, bans reported at low volume even for reply-only bots) and Meta litigates **vendors**, not just senders. No mainstream connector platform ships it.

This is the same boundary as the LinkedIn people-search decline (FAQ #19): a user consenting to *their own* account is not Meta authorizing an unofficial client, and the counterparties in those chats never consented to entering an agent pipeline. Handing an agent a linked-device session also hands it a total-account credential — a prime prompt-injection and exfiltration target.

**What we ship instead, and it is not a consolation prize:**

| The ask | The honest answer |
|---|---|
| "Send from my personal number" | `whatsapp` — build a `wa.me` link or QR; the agent composes, the human taps send. Officially documented, zero network calls. |
| "Automate my number for real" | Convert it: install the free WhatsApp Business App (chats and history migrate on-device), then onboard through **Embedded Signup with coexistence** — the same number keeps working on the phone *and* gains Cloud API access, with up to 6 months of history synced. |
| "Read my chat history" | WhatsApp's own in-app **Export chat** produces a file the user consciously exports; parsing that offline is a legitimate future primitive. |

So the answer to "can a normal user connect their WhatsApp?" is **yes — by converting the number in about three minutes, not by impersonating a phone**.

**References:** decision D00008W (locked), `connectors/whatsapp/README.md`, `.agent/artifacts/whatsapp-connector-plan.md` §1.

## 23. Why publish the docstring prose in the tool description (and how is it bounded)?

**Decision: the LLM-facing tool description is the `@action` title *plus* the docstring prose above `Args:` — because a model can't read our source, so any usage contract that lives only in the docstring is invisible and produces wrong or destructive calls.**

Previously `serve/_filtering.py::_build_description` published only `"{connector}: {title}"`. Measured on the 0.3.23 catalog, 93% of actions (1,425/1,530) had docstring prose — query syntax, value formats, "returns base64", PUT-vs-PATCH semantics, "use `X` instead" — that was written by the authors and then dropped before it reached the model. The failure mode was concrete: `gdrive.search_files` published "Search files in Google Drive", so a model sent `"quarterly report"` and Drive returned HTTP 400 — the schema didn't contain the answer, and the model couldn't diagnose it. The information already existed; we just weren't publishing it.

Three guards keep it from becoming noise, honouring the same token-cost discipline that keeps `requires_scope`/`dangerous` *out* of the string (they're structured fields):

- **Capped** (~900 chars, clean-boundary truncation) so one docstring with several code-block examples can't dominate a tool list re-sent every turn — catalog p99 is ~480 chars, so only the rare outlier is trimmed.
- **Title-deduped** — a summary line that merely restates the `@action` title is dropped, so the same sentence is never emitted twice.
- **Excluded from `site/data.json`** — the website renders only title/params/return-type, so the prose ships to MCP/function-calling callers but not as dead weight in the committed site catalog.

The `Args:` block is unchanged — it still flows to the parameter schema. And Tier-1 (live-verified) connectors are held to a real usage-contract docstring by a conformance ratchet (`tests/conformance/test_docstring_quality.py`) that only tightens toward zero thin docstrings.

**References:** `serve/_filtering.py`, `runtime/action.py` (`_extract_docstring_prose`), `spec/action.py` (`ActionSpec.long_description`); guide `docs/guides/adding-connector.md` ("Your docstring is the tool contract").

## 24. Why a separate `access` (read/write/destructive) field when `dangerous` already exists?

**Decision: `dangerous` is a *destructive* flag only ("delete, send, etc."), so it can't answer "is this read-only?". We add an explicit `access: "read" | "write" | "destructive"` field so a consumer enforcing read-only has a contract, not a naming heuristic.**

A platform embedding our tools often needs to run some agents read-only. `dangerous` doesn't support that: measured on 0.3.24, 30+ Tier-1 actions were name-obvious writes carrying `dangerous=False` (`notion_update_page`, `github_update_issue`, `stripe_create_setup_intent`, …). The fallback — a read-verb allowlist (`list_/get_/search_/…`) — is brittle both ways: a real read whose name doesn't match a known verb is dropped, and a mutation shipped under a read-looking verb passes (we'd already had to remove `export_/check_/download_/query_` after finding mutations under them — `export_certificate` returns a private key; `check_verification` POSTs and consumes a one-time code). Neither existing field can back a read/write signal: `requires_scope` is unset on 71% of actions and `idempotent` on ~95%.

So `access` is set **explicitly and grounded in each action's real side effect**, not its verb — a POST that only searches / reveals / computes / runs inference (`notion.search`, `lusha.enrich_contacts`, `gemini.generate_content`, a GraphQL query, `odoo.search_read`) is `read`, because it persists nothing vendor-side. `dangerous` auto-derives `access="destructive"`, and a conformance ratchet (`tests/conformance/test_access_classification.py`) enforces that the two always agree and that **every Tier-1 (live) action is classified** (read 233 / write 74 / destructive 132 at introduction). Non-Tier-1 actions stay `None` until classified; a read-only consumer treats `None` as "not provably read" and fails closed. `access` and `idempotent` are both surfaced in `list_tools()` / `ToolEntry.to_dict()`.

**References:** `spec/action.py` (`AccessKind`, `ActionSpec.access`), `runtime/action.py` (`@action(access=...)` + destructive auto-derive), `serve/_filtering.py` (`ToolEntry.to_dict`), `tests/conformance/test_access_classification.py`.
