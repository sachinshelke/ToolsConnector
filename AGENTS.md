<!-- codevira:begin (auto-generated; do not edit) -->

## Codevira-tracked project memory: toolsconnector

> **Codevira** — cross-IDE persistent memory. Read it with the codevira MCP tools (`get_session_context`, `search_decisions`); do **not** open `.codevira/*.jsonl` directly — those files are large and token-heavy.

### Locked decisions (do_not_revert)

- **D000001** LinkedIn connector promoted to Tier 1 (verification_status="live") — live re-verified 2026-06-20.  ·  `src/toolsconnector/connectors/linkedin/connector.py`  ·  _connector, linkedin, live-verified, oauth, tier-1, verification_
- **D000002** Added linkedin_leads connector (LinkedIn Lead Sync API) for consented lead data; refused to build any arbitrary people-…  ·  `src/toolsconnector/connectors/linkedin_leads/connector.py`  ·  _connector, lead-sync, linkedin, marketing, privacy, scope-boundary_
- **D000003** Hardened linkedin_leads after a 6-agent adversarial audit vs LinkedIn's live Lead Sync docs — fixed the leadType enum (…  ·  `src/toolsconnector/connectors/linkedin_leads/connector.py`  ·  _audit, connector, correctness, hardening, lead-sync, linkedin_
- **D000005** LinkedIn is organized Google-style: separate connectors split by CREDENTIAL/product family, each holding all capabiliti…  ·  `src/toolsconnector/connectors/linkedin/connector.py`  ·  _architecture, connector, linkedin, roadmap_
- **D000006** Hardened both LinkedIn connectors after a 25-agent adversarial quality audit — fixed media-upload robustness, credentia…  ·  _audit, connector, hardening, linkedin, robustness, security_
- **D000008** Doc-audited contactout + lusha against their LIVE API docs and fixed confirmed bugs + completed full API surface. The r…  ·  `src/toolsconnector/connectors/contactout/connector.py`  ·  _bugfix, connector, contactout, doc-audit, lusha, people-data_
- **D000009** Chaos/resilience-hardened contactout + lusha: found 13 real defects via an adversarial chaos sweep (probe harness + 8-d…  ·  `src/toolsconnector/connectors/_helpers/sanitize.py`  ·  _chaos-testing, contactout, credential-leak, lusha, people-data, resilience, security_
- **D00000A** Added a universal stall guard + max_pages ceiling to the SHARED PaginatedList.collect()/collect_sync() (src/toolsconnec…  ·  `src/toolsconnector/types/paginated.py`  ·  _chaos-testing, hang-guard, pagination, resilience, types_
- **D00000E** Lusha live-verified against the production API + promoted Tier 2 (doc) → Tier 1 (live) on 2026-06-24 (commit 7b96ab1, p…  ·  `src/toolsconnector/connectors/lusha/connector.py`  ·  _live-verification, lusha, people-data, verification-tier_

### Active conventions

- **D000004** LinkedIn connector roadmap (surveyed 2026-06-20): buildable next = linkedin_conversions (self-serve, verifiable today) …  ·  _connector, linkedin, roadmap, scope-boundary, survey_
- **D000007** Built contactout + lusha connectors (BYOK contact-enrichment vendors). Distinct from the D000002 no-people-search bound…  ·  `src/toolsconnector/connectors/contactout/connector.py`  ·  _byok, connector, contactout, enrichment, lusha, people-data_
- **D00000B** ContactOut connector live-verified with a real key (2026-06-24): the key is a sales-DEMO key returning canned 'sample r…  ·  `src/toolsconnector/connectors/contactout/connector.py`  ·  _byok, contactout, live-verification, people-data_
- **D00000C** ContactOut deeper live field-audit (2026-06-24, commit 910ee9c): captured the real wire envelope for all 19 endpoints v…  ·  `src/toolsconnector/connectors/contactout/connector.py`  ·  _contactout, false-green, live-verification, people-data_
- **D00000D** ContactOut promoted Tier 2 (doc) → Tier 1 (live) on a CONTRACT-SCOPED basis (commit d0c5802, 2026-06-24). Rationale: th…  ·  `src/toolsconnector/connectors/contactout/connector.py`  ·  _contactout, live, people-data, verification-tier_
- **D00000F** Add `toolsconnector.auth` module in two layers: (1) request-signing providers (BearerToken, ApiKey, BasicAuth, HMACSign…  ·  `src/toolsconnector/auth/`  ·  _architecture, auth, backlog, byok_


For the full decision log, use `search_decisions` / `list_decisions` (or the `codevira` CLI) — don't read `.codevira/*.jsonl` directly.

<!-- codevira:end -->
