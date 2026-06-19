# Multi-Language SDK Rollout — Python → TypeScript + Go from one source

> Status: PLAN (not started). Builds on: ADR #17 (ARCHITECTURE_FAQ #17),
> [`phase1-binding-migration.md`](phase1-binding-migration.md) (the Python
> prerequisite), and `experiments/sdk_spike/` (proven: 13/13 request byte-parity;
> `gen_ts.py` emits a native TS SDK at 10/10 parity).
> **Target chosen: TypeScript + Go together.**
> **Goal:** every new connector, authored once as a binding, ships as idiomatic
> **Python + TypeScript + Go** packages that pass ONE shared conformance suite and
> publish together — so "release a new tool" means "release it in all languages."

---

## 0. Where this sits (and the honest prerequisite)

Phase 1 (separate doc) makes the binding **load-bearing in Python** — the runtime
builds/sends/paginates/error-maps from the declarative `HttpBinding`, not from
hand-written `_request` bodies. **Until that lands there is nothing to re-emit in
another language.** This document is Phases 2–6: the TS + Go generators, runtimes,
the cross-language guarantee, joint publishing, and the new-connector authoring
flow. It assumes Phase 1's binding IR (`spec/binding.py`) + runtime
(`runtime/serialization/`) exist and drive ≥10 connectors.

## 1. Definition of done

- A connector defined purely by its binding IR generates **3 packages**.
- All 3 pass the **same** golden conformance corpus (byte-identical canonical HTTP).
- **One tag** publishes PyPI + npm + a Go module version together.
- Authoring a NEW connector = write a binding (+ rare override) → 3 packages, with
  **zero per-language hand-coding for the declarative 92–97%**.

## 2. The cross-language guarantee — a shared conformance corpus (the linchpin)

Three independent runtimes WILL drift unless something forces them to agree. That
something is a language-agnostic golden corpus — the single most important artifact
in this plan.

- **Format:** `conformance/<connector>.json` — a list of cases
  `{action, credential_fixture, inputs}` → expected **canonical request**
  `{method, url, headers (sorted, auth normalized/redacted), body (normalized)}`.
- **Derivation:** generated from the **Python reference** (the spike's `parity.py`
  is already this oracle) once Phase 1 makes bindings load-bearing.
- **Use:** every language's generated client replays the corpus against a mock
  transport and asserts byte-parity. **CI fails any language that diverges.** This
  turns "same behavior everywhere" into a tested invariant, not a hope.
- **Plus** an optional keyed live smoke per Tier-1 connector per language to catch
  real-API edges a mock can't (reuses the Tier-1 live-verification discipline).

## 3. The generator (one, Python-hosted)

- Extends `experiments/sdk_spike/gen_ts.py` into a multi-target emitter. Input:
  the binding IR. Output: per-target source via templates.
- A **target** is pluggable = `{type/template set, param-binding emitter, runtime
  import map, package scaffolding, conformance-harness emitter}`. **Adding a
  language = add a target + a runtime**, nothing else.
- Emits: typed models (from response schemas), per-action methods (from bindings),
  package manifest, the conformance harness wired to the shared corpus, doc stubs.

## 4. The per-language thin runtime (authored once per language)

Each runtime implements the SAME contract `runtime/serialization/` defines in
Python: transport; auth signers (Bearer, header-key, basic-split, **SigV4**, HMAC);
the 3 pagination drivers (offset-token / link-header / follow-URL); retry +
circuit-breaker + timeout; typed-error mapping; serialization styles (indexed
`[i]`, indexed-object `[i][k]`, bracket `[]`, form-explode); body encoders
(json/form); response unwrap. Kept **thin** — the spike's ~300-line runtime drove
2,264 lines of connectors (~7:1); budget each runtime in the low-hundreds of LOC.

### TypeScript target
- `@toolsconnector/runtime` (runtime lib) + `@toolsconnector/sdk` (generated), with
  per-connector subpath exports for tree-shaking.
- Dual ESM+CJS build; `.d.ts` from the IR; params as TS interfaces (optionally
  `zod` for runtime input validation parity with Pydantic). Async-only.
- Transport: native `fetch`/undici. **SigV4 via `aws4fetch`** (don't hand-roll).
- Typed error-class hierarchy mirroring `toolsconnector.errors`.

### Go target
- Module `github.com/<org>/toolsconnector-go`; one sub-package per connector + a
  shared `runtime` package.
- `context.Context`-first methods; optional params via a per-action `Params` struct;
  typed sentinel errors with `errors.Is`/`errors.As`. Sync (idiomatic Go).
- Transport: `net/http`. **SigV4 via `aws-sdk-go-v2`'s signer.**
- No async wrappers (blocking + goroutines is the Go model).

## 5. Escape hatches per language (the measured 2.6%)

39 actions — 23 sequential-request orchestration + 16 computed material
(base64/uuid/hash/hmac). The generator emits a stub and wires a **hand-written
override file keyed `connector.action`** in each language. These are the ONLY
hand-written per-language code. CI lists which actions are override-backed per
language so the tally is visible and can't silently grow past the 2.6%.

## 6. Monorepo + joint publishing

- **Recommend MONOREPO:** `sdks/python`, `sdks/typescript`, `sdks/go`, all generated
  from `spec/bindings/*` + `conformance/*`. One source tree, one CI.
  - Go nuance: Go consumes via VCS tags, not a registry. Either tag the monorepo
    subdir module (`sdks/go/vX.Y.Z`) or **mirror** `sdks/go` to a dedicated tagged
    module repo on publish (cleaner `go get`). Decide the module-path/tag scheme
    up front (open decision #3).
- **Versioning: lockstep minor** (one product version; a binding change re-emits
  all), per-language **patch** allowed for runtime-only fixes. release-please on
  the meta version.
- **Release flow:** binding/connector change → `make generate` → run ALL conformance
  corpora + each language's unit tests → on green, publish PyPI + npm + Go tag from
  one tag (OIDC/attestations per ecosystem; matches today's PyPI pipeline).

## 7. The new-connector authoring flow (the payoff)

1. Author `spec/bindings/<connector>.json` (+ response models) — the only hand-work
   for the declarative 92–97%.
2. (rare) add escape-hatch overrides for non-declarative actions, per language.
3. `make generate` → Python + TS + Go packages + conformance harness.
4. Parity gate + tests pass.
5. Joint release publishes all three.

New connectors MUST be authored as bindings for this to hold — the workflow shift
Phase 1 establishes. This is the literal answer to "new tool ships in all languages."

## 8. Phased delivery (each independently verifiable)

- **Phase 1** (prereq, separate doc): bindings load-bearing in Python; real
  full-scale escape-hatch number; build-vs-reuse decision gate.
- **Phase 2 — Corpus + contract freeze.** Generate goldens from the Python
  reference for all migrated connectors; write the runtime-contract spec all 3
  languages implement.
- **Phase 3 — TypeScript end-to-end.** Promote `gen_ts.py` to a real target; write
  `@toolsconnector/runtime`; generate `@toolsconnector/sdk`; pass the full corpus;
  preview-publish to npm. (TS leads — prototype exists.)
- **Phase 4 — Go end-to-end.** Go runtime + target; pass the SAME corpus;
  preview-publish (tag scheme decided).
- **Phase 5 — Joint CI + authoring flow.** One tag → 3 publishes; `make generate`
  in CI; "author a connector as a binding" docs.
- **Phase 6 — Backfill + new-connector default.** Generate TS+Go for all migrated
  connectors; make binding-authoring the default; retire imperative connectors as
  they migrate.

TS and Go run in parallel after Phase 2 (you chose both); TS leads by one phase
since its generator exists, and Go validates the generator is truly
language-agnostic rather than TS-shaped.

## 9. Risks & mitigations

- **Runtime drift across 3 languages** (biggest) → the shared conformance corpus is
  the single guard; CI fails any divergence.
- **Idiomaticity vs uniformity** → templates per language (not transpilation);
  per-language reviewer.
- **SigV4 ×3** → reuse vendor signers (`aws-sdk-go-v2`, `aws4fetch`); never
  re-implement HMAC crypto.
- **Escape-hatch sprawl** → cap + log per language; alert if the 2.6% grows.
- **N thin-runtime maintenance** → keep thin (~7:1 ratio); fixes go to the
  generator/runtime, not per connector.
- **GraphQL connectors** (linear, shopify, parts of github) → the binding IR is
  REST-shaped. v1: keep GraphQL connectors imperative/escape-hatch, OR add a
  GraphQL binding kind (open decision #5). Don't let it block the REST 90%.
- **MCP/agent surface per language** → out of scope v1; Python keeps the MCP
  server. Revisit whether TS/Go need agent adapters.

## 10. Open decisions (these gate the start)

1. **Repo layout** — monorepo (recommended) vs poly-repo (+ Go mirror either way).
2. **Versioning** — lockstep minor (recommended) vs fully independent per language.
3. **Package identities** — npm scope (`@toolsconnector/*`?), Go module path + tag
   scheme (subdir-tag vs mirrored module repo).
4. **Cadence** — TS+Go simultaneously, or TS leads by one phase (recommended) on the
   same corpus.
5. **GraphQL in v1** — escape-hatch/imperative, or build a GraphQL binding kind now?
6. **TS runtime validation** — `zod` to match Pydantic input validation, or
   types-only?

## 11. Effort (honest)

- **Phase 1 is the big rock** (binding extraction across 73 connectors) — weeks.
- Each language runtime+generator is medium; TS cheaper (prototype exists), Go from
  scratch.
- Net: a **multi-week program**. The "new tool → 3 languages free" payoff starts
  only after Phases 1–4 land for the first batch — but from then on it compounds on
  every connector.
