# Phase 1 — Make the binding the source of truth in Python

> Status: SCOPED (not started). Prereq evidence: `experiments/sdk_spike/` + ADR #17.
> Goal of Phase 1: prove the declarative HTTP-binding layer is **load-bearing in
> Python** — drive the real runtime off it — before generating any other language.
> This yields the real escape-hatch number at full scale and removes a whole class
> of per-connector bugs (see the 4 fixed in `d9eb362`).

## Why Python-first (not straight to TS/Go)

The spike proved the binding can *describe* requests (13/13 byte-identical) and
that a generator can *emit* a native SDK (TS, 10/10 parity). What it has NOT
proved: that the binding can **drive a real connector end-to-end** (auth, send,
paginate, error-map, parse) as a drop-in for the imperative code. If the binding
is load-bearing in Python, every other language is "just" a re-emit of the same
runtime. If it isn't, we learn that now — in the language with the most tests.

## Approach: incremental, parity-gated (Strategy C)

Rejected: (A) pure AST auto-extraction of bindings from imperative code — lossy,
never 100%, unverifiable. (B) big-bang rewrite of 68 connectors — too risky.

**Chosen (C):** introduce the binding as an *optional declaration* per action.
When present, `BaseConnector` builds+sends via the shared executor; when absent,
the existing imperative method runs unchanged. Migrate connector-by-connector,
and **gate every flip on byte-parity against the existing imperative code** — the
spike's parity oracle becomes the migration safety net. The imperative method is
the oracle during migration, then deleted once the binding drives it.

This means: zero big-bang risk, every step is reversible, and the existing
1,970-test suite + the parity gate guard each connector as it moves.

## Mechanism (the new building blocks)

1. **`spec/binding.py`** — promote `experiments/sdk_spike/binding_ir.py` into the
   real `spec/` package (the IR already lives there per FAQ #7). Add
   `HttpBinding` to `ActionSpec` (optional field; default `None`).
2. **`runtime/serialization/`** (currently an EMPTY placeholder) — promote
   `experiments/sdk_spike/executor.py` here as the real request builder, plus a
   response-unwrap + the 3 pagination drivers. This is the per-language runtime,
   authored once in Python.
3. **`@action(..., binding=HttpBinding(...))`** — the decorator accepts a binding.
   `BaseConnector` gains a `_execute_binding(action, args)` path: build via the
   serializer, send via the existing transport/middleware (retry, rate-limit,
   auth provider — all already exist), unwrap, paginate. Imperative `_request`
   stays as the fallback + escape hatch.
4. **Escape hatch** — an action may keep its imperative body (no binding) OR
   declare a binding + a `post`/`pre` hook for the genuine <2.7%. Both supported.

## Migration loop (per connector, mechanical + gated)

For each connector, in coverage-ascending order of difficulty:
1. Author bindings for its DECLARATIVE actions (the 92% — `coverage.py` lists them).
2. Run the **migration parity gate** (generalize `experiments/sdk_spike/parity.py`):
   for every action, assert `imperative_request == binding_request` via
   `httpx.MockTransport`. Must be byte-identical before flipping.
3. Flip those actions to the binding path; leave REVIEW/ESCAPE_HATCH actions
   imperative (or add hooks).
4. Existing connector test suite must stay green.
5. Once all of a connector's actions are binding-driven, delete the dead
   imperative `_request`/`_fetch_*` scaffolding.

Order: start with the 3 already-spiked (airtable, twilio, shopify — bindings
exist), then the rest by coverage %. Track the live escape-hatch tally.

## Decision gate (after ~10 connectors migrated)

With real Python data in hand, decide **build vs. reuse** for codegen:
- (build) keep the Pydantic IR + write per-language emitters (we have the TS one).
- (reuse) transpile the IR → Smithy IDL and reuse `smithy-{ts,go,java}` generators
  (native SigV4 + paginators) — evaluate whether they cleanly target arbitrary
  3rd-party REST/GraphQL, not just AWS protocols.

Then resume the language rollout (TS first — generator already prototyped).

## Risks & mitigations

- **Hidden imperative nuance** (a binding that's byte-parity on mocked requests
  but diverges on a real edge) → the parity gate uses the SAME inputs the tests
  use; keep live-verified (Tier 1) connectors' live checks in the loop.
- **Middleware/auth-provider interplay** → reuse the existing transport/middleware
  pipeline unchanged; the binding only replaces request *construction*, not I/O.
- **Scope creep into a rewrite** → optional-binding + per-action flip keeps it
  incremental; never block a connector on its hard 20%.
- **MCP/function-schema surface must not change** → bindings add the HTTP layer
  only; `get_spec()` interface output stays identical (regression-test it).

## First concrete step (the keystone)

Promote `binding_ir` → `spec/binding.py` and `executor` → `runtime/serialization/`,
wire the `@action(binding=...)` path + `_execute_binding` into `BaseConnector`,
and migrate **Airtable** end-to-end (it has the gnarliest patterns) behind the
parity gate + its (new) full test suite. If Airtable flips clean, the pattern is
proven and the rest is mechanical.
