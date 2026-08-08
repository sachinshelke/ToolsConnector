# Tier 1 API Freshness Monitor — Plan

Status: PLAN (not built) · Created 2026-08-03 · Scope: Tier 1 (Google) only
Related: `oauth-flow-tier-a-plan.md` (OAuth endpoint drift is a subset of this)

## 1. Objective

Automatically detect when a Tier 1 tool's **API changes** — version/revision,
endpoints, scopes, methods, parameters, schemas — and flag the **impact on our
connectors**, so both code AND docs stay in sync with the provider. Turns "stay
updated" from a manual promise into an automated, scheduled guarantee.

## 2. Scope

- Tier 1 = the 6 Google connectors: gmail, gcalendar, gdrive, gdocs, gsheets, gtasks.
- Generalizes to Tier B later (§11), but Google first because it has the cleanest
  machine-readable source of truth.

## 3. Source of truth — Google Discovery Documents

Google publishes a **machine-readable spec per API**, containing a `revision`
(YYYYMMDD), `version`, every method (+ its `parameters` and `scopes`), and all
`schemas`. Diffing two snapshots = precise, structured change detection.

| Connector | API / version | Discovery doc (confirm exact URL at build) |
|---|---|---|
| gmail | gmail v1 | `https://www.googleapis.com/discovery/v1/apis/gmail/v1/rest` |
| gcalendar | calendar v3 | `.../discovery/v1/apis/calendar/v3/rest` |
| gdrive | drive v3 | `.../discovery/v1/apis/drive/v3/rest` |
| gdocs | docs v1 | `https://docs.googleapis.com/$discovery/rest?version=v1` |
| gsheets | sheets v4 | `https://sheets.googleapis.com/$discovery/rest?version=v4` |
| gtasks | tasks v1 | `https://tasks.googleapis.com/$discovery/rest?version=v1` |

> UNVERIFIED: Google is migrating from the legacy `discovery/v1/apis/...` index to
> per-service `$discovery/rest?version=` endpoints. Confirm the live URL for each
> API as step 0 of the build. Also fetch the directory
> `https://www.googleapis.com/discovery/v1/apis` to catch new versions (e.g. v3→v4).

## 4. Architecture — two layers

**Layer 1 — mechanical (the reliable backbone). GitHub Actions cron.**
1. Fetch each connector's discovery doc.
2. Normalize + diff against a committed baseline snapshot
   (`.agent/api-baselines/<api>.<version>.json`).
3. Emit a structured drift report: revision/version delta; added / removed / changed
   methods, parameters, scopes, schema fields.
4. **Impact map:** cross-reference changes against the actions/scopes WE expose, so
   the report says not just "Google changed X" but "Google changed X *that we surface
   in `gmail.list_messages`*".
5. On drift → open a GitHub issue (and/or a PR bumping the baseline) with the report.
   No drift → no-op.

**Layer 2 — intelligent (optional). Scheduled Claude routine.**
- Reads Layer 1's drift report, assesses impact ("drive deprecated param we use →
  action required" vs "new method we don't expose → optional add"), and drafts the
  connector + README + ROADMAP updates as a PR. This is the "understand what changed"
  the requirement calls for. Add after Layer 1 is proven.

## 5. Scheduling — CI cron vs Claude routine (important distinction)

- **GitHub Actions cron = durable.** Runs forever in the repo, independent of any
  Claude session. This is the backbone for "always updated." → Layer 1.
- **Claude routine/scheduled agent = intelligent but session-bound.** Great for the
  assessment/drafting in Layer 2, but must not be the *only* trigger — it doesn't run
  if no one schedules it. → Layer 2 only.

## 6. Docs-in-sync — what a detected change updates

One PR touches all of: connector code (if behavior changed) · connector README
(scopes/endpoints/actions) · ROADMAP tier notes · docs/ARCHITECTURE_FAQ (if a
decision changes). Layer 2 drafts these together so code and docs never diverge.

## 7. Where it lives

- `scripts/check_api_drift.py` — fetch + normalize + diff + report (mirrors the
  existing `*_binding_parity.py` / `odoo_live_probe.py` pattern).
- `.agent/api-baselines/*.json` — committed baseline snapshots (the diff anchor).
- `.github/workflows/api-drift.yml` — weekly cron calling the script.

## 8. Dependencies

httpx (core) + stdlib (json, difflib, hashlib). **Zero new runtime deps** — and it's
dev/CI tooling, so nothing ships in the library regardless.

## 9. Cadence

Weekly (Google revisions are frequent but not daily; weekly balances signal vs noise).
Configurable; can raise to daily for specific APIs if churn warrants.

## 10. "Done when"

- Baselines committed for all 6 Google APIs.
- `scripts/check_api_drift.py` fetches, diffs, and reports; exits non-zero on drift.
  Test: feed it a hand-mutated baseline (rename a method, drop a scope) → it detects
  and names exactly that change.
- `.github/workflows/api-drift.yml` runs weekly and opens an issue on drift.
- Impact map correctly flags a change to a method/scope we expose vs one we don't.

## 11. Generalization to Tier B (later)

Each Tier B tool needs a spec source: OpenAPI/Swagger where published (Slack, Stripe,
GitHub have machine-readable specs), else changelog scraping or a version-endpoint
probe. Same differ + reporter; only the fetch adapter differs per provider.

## 12. Open decisions

- Notification target: GitHub **issue** vs auto-**PR** bumping baseline vs Slack. (Rec:
  issue + auto-PR bumping baseline, so the diff is reviewable.)
- Layer 2 (Claude routine) in scope now, or after Layer 1 proves out? (Rec: Layer 1 first.)
- Cadence: weekly vs daily.
- Baseline format: raw discovery JSON vs a normalized/trimmed projection (Rec:
  normalized — strips noise like descriptions so diffs are meaningful).
