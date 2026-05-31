# Multi-language SDK — de-risking spike

**Question (make-or-break):** before committing to a "build once → all languages"
SDK generator, can the *imperative* request logic of ToolsConnector's **hardest**
connectors be captured in a **bounded, declarative** vocabulary — or does it need
open-ended imperative escape hatches, and for how much?

**Answer:** **13/13** representative requests across the 3 hardest connectors
(Airtable, Twilio, Shopify) are fully expressible declaratively. **0 escape
hatches.** A ~300-line language-agnostic executor reproduces the *exact* HTTP
requests the hand-written connectors send — and in 4 cases produced the *correct*
request where the connector had a latent bug.

> This is a **spike / experiment**. It imports the real connectors read-only and
> touches **nothing** in `src/` or the 68 connectors.

## Run

```bash
.venv/bin/python -m experiments.sdk_spike.parity
```

## What it proves

`spec/` today captures the connector **interface** (names, types, JSON Schema,
pagination *enum*) — perfect for generating function-calling/MCP schemas + docs,
but it captures **none** of the HTTP **binding** (method, path template, param
location, serialization style, body wrapping/encoding, per-action base URL,
response unwrap, pagination plumbing). That binding lives only in imperative
`_request`/`@action` bodies; `runtime/serialization/` is an empty placeholder and
`codegen/.../generate_openapi()` models actions as RPC to the *TC server*, not the
real upstream.

This spike adds the **missing binding layer** as a small finite vocabulary and
shows a generic executor driven by it == the imperative connectors.

| File | Lines | Role |
|---|---|---|
| `binding_ir.py` | ~120 | the missing binding schema (extends `spec/`) |
| `executor.py` | ~180 | language-agnostic runtime — the **only** per-language code |
| `specs.py` | ~190 | declarative bindings for 9 actions (transcribed from the connectors) |
| `parity.py` | — | oracle: drives the real connectors via `httpx.MockTransport`, asserts byte parity |
| `coverage.py` | — | AST classifier over all 68 connectors → declarative-coverage %|
| `gen_ts.py` | — | generates a native TypeScript SDK (`ts/`) from the same bindings |
| `ts_parity.py` | — | cross-language oracle: generated TS runtime vs Python executor |
| `ts/` | — | the generated TS SDK: runtime + typed client per connector |

~300 lines of runtime+schema drive what is **2,264 lines** of imperative code for
just these 3 connectors → the leverage (and the "lightweight" requirement) is real.

## Hard patterns expressed (21)

indexed query `fields[i]` · indexed-object query `sort[i][field]` · bracket/batch
`records[]` · JSON body key placement · per-item body wrap `{records:[{fields:…}]}`
· single-key body wrap `{product:…}` · form-encoded bodies · multiple base URLs
(Airtable data/meta, Twilio main/verify) · base-URL templating `{store}` · path
templating from creds `/Accounts/{account_sid}/…` · size clamps · custom auth
header · basic-auth from split creds · offset-token / link-header / follow-URL
pagination · response unwrap · …

## Full-scale coverage — does it hold beyond the 3 hardest?

`coverage.py` is a transparent AST classifier over **every** `@action` in **all 68
connectors** (run: `.venv/bin/python -m experiments.sdk_spike.coverage`). It buckets
each action by whether a *single* declarative `ActionBinding` can express it, keying
off objective imperative "smells" and printing the reason for every flagged action.

| Bucket | Count | % | Meaning |
|---|---|---|---|
| **DECLARATIVE** | 1290 | **92.0%** | 1:1 `ActionBinding`, no imperative smell |
| **REVIEW** | 74 | 5.3% | soft smell — almost all declarable w/ a small vocab add |
| **ESCAPE_HATCH** | 38 | 2.7% | needs an imperative override (conservative ceiling) |

**≈1,402 actions → 92% pure declarative; 97% incl. REVIEW; ≤2.7% true escape hatch.**

The 2.7% is a deliberate **over**-estimate. Spot-checking the flagged actions:
- Some "2 sequential requests" are actually **arg-routed branches** where only one
  request executes (e.g. `stripe.cancel_subscription` = `POST` vs `DELETE` on a bool)
  → declarable as a conditional/dual binding, not orchestration.
- Most "inline crypto" flags are **bounded param transforms** that belong in the
  runtime, not the action: `base64` (attachment encode/decode — gmail/gdrive/ec2),
  `uuid` (idempotency `CallerReference` — cloudfront/route53), `hashlib` (Mailchimp's
  documented MD5-of-email subscriber id).
- REVIEW "no request detected" (github/dockerhub `list_*`) = **delegation** to a
  shared pagination helper → declarable; strengthens the floor.

The genuinely irreducible core is a handful of **multi-request orchestrations** —
`gmail.list_emails` (N+1: list ids → hydrate each), `gdrive.move_file` (GET parents →
PATCH), `outlook.list_*` (resolve folder → list). These need a 2-step **pipeline**
composition or a per-action escape hatch (Smithy/Stainless both ship one).

**Conclusion: the declarative binding holds at full scale.** Adding the binding layer
makes ~97% of the surface generatable; the escape hatch covers the rest.

## TypeScript generator — build once → native SDK

`gen_ts.py` reads the SAME bindings and emits a real, in-process TypeScript SDK
under `ts/`: a runtime port of `executor.py`, one typed client class per connector
(typed `*Args` interfaces + camelCased `async` methods), and the inlined binding.
`ts_parity.py` closes the loop.

```bash
.venv/bin/python -m experiments.sdk_spike.gen_ts        # emit the TS SDK
node experiments/sdk_spike/ts/src/parity.ts             # Node 23 type-strips & runs it
.venv/bin/python -m experiments.sdk_spike.ts_parity     # cross-language parity vs Python
cd ts && npx tsc --noEmit                               # strict type-check
```

- **10/10 requests byte-identical** between the Python executor and the generated
  TypeScript runtime — same bindings → same HTTP, in two languages.
- **`tsc --noEmit` (strict) passes** — the generated SDK is fully type-safe.
- The runtime uses only `fetch` / `URL` / `btoa` (no Node-only globals) → the same
  code runs in Node, Deno, Bun, and the browser. **In-process, nothing hosted.**

End-to-end proof of "build once, generate any language": one declarative source →
a native, typed, in-process SDK whose requests match Python exactly.

## Latent connector bugs surfaced (executor is correct)

1. **Shopify** — `Shopify(credentials="token:store")` never substitutes `{store}`;
   every request targets host `{store}.myshopify.com`. `BaseConnector.__init__`
   pre-fills `_base_url` with the class template, so `Shopify._setup`'s
   `.format(store=…)` branch is dead code.
2. **Twilio** — following `next_page_uri` via `client.get(uri)` doubles the
   `/2010-04-01` prefix (httpx merges `base_url` by concatenation, not RFC join),
   so page 2+ of `list_messages`/`list_calls` would 404.

A single audited executor eliminates this entire **class** of per-connector bugs —
itself an argument for the generator approach.
