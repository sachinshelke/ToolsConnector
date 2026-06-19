# ToolsConnector Growth & Distribution Playbook

A concrete, do-this-next checklist for getting ToolsConnector found and adopted.
On-page SEO is already strong (sitemap, robots, JSON-LD, OG tags, per-connector
static pages, breadcrumbs). The leverage now is **distribution** (backlinks +
referral traffic) and **content cadence**. SEO compounds slowly; distribution
moves the needle in weeks.

Ordered by impact-per-hour. Check items off as you go.

---

## 1. PyPI listing (30 min — highest ROO, the install funnel)

The PyPI page is where pip users land. Make it sell.

- [ ] **Long description** = the README (already rendered). Ensure the first
      screenful has: one-line value prop, the 3 install commands, a 6-line code
      sample, and the badge row.
- [ ] **`pyproject.toml` metadata** — confirm these are set:
  - `keywords = ["api", "connectors", "ai-agents", "mcp", "llm-tools", "openai-function-calling", "anthropic-tool-use", "integrations", "python"]`
  - `classifiers` — include `Development Status`, `Intended Audience :: Developers`,
    `Topic :: Software Development :: Libraries`, `Programming Language :: Python :: 3.9/3.10/3.11/3.12`,
    `License :: OSI Approved :: Apache Software License`.
  - `[project.urls]` — `Homepage = https://toolsconnector.github.io`,
    `Documentation`, `Repository`, `Changelog`, `Issues`. PyPI renders these as sidebar links.
- [ ] **Project icon** — PyPI shows the project's avatar; ensure the GitHub org/repo has a logo.

## 2. GitHub repo optimization (30 min — the star funnel + SEO backlink)

- [ ] **About section** (gear icon top-right): crisp description + `https://toolsconnector.github.io` website link + **topics**:
      `python`, `ai-agents`, `mcp`, `llm`, `openai`, `anthropic`, `api-client`,
      `connectors`, `integrations`, `function-calling`, `model-context-protocol`,
      `langchain`. Topics are GitHub-searchable and SEO-indexed.
- [ ] **Social preview image** (Settings → Social preview, 1280×640): a branded
      card with the logo + "74 connectors, one interface" + the 3 framework logos.
      This is what renders when the repo is shared on X/LinkedIn/Slack.
- [ ] **README badges** (top of README): PyPI version, downloads, Python versions,
      license, CI status, **stars**. Same shields.io set now on the site hero.
- [ ] **Pin** the repo on your profile/org.
- [ ] **Releases**: each release tag should have human-readable notes (release-please
      generates these — make sure they're publishing). Releases get their own
      indexable URLs.

## 3. Directory & list submissions (1–2 hrs — durable backlinks)

These are high-authority backlinks + targeted discovery. Submit once, benefit forever.

- [ ] **MCP registry / awesome-mcp-servers** — ToolsConnector is an MCP server
      provider for 74 tools. This is the single most on-target list given the
      MCP positioning. (github.com/punkpeye/awesome-mcp-servers and the official
      modelcontextprotocol/servers list.)
- [ ] **awesome-python** (vinta/awesome-python) — under "Third-party APIs" or "RESTful API".
- [ ] **awesome-llm / awesome-llm-tools / awesome-ai-agents** — the agent-tooling angle.
- [ ] **LibHunt, Openbase, PyPI Trending** — auto-index from PyPI; ensure metadata is clean.
- [ ] **AlternativeTo / Product comparison sites** — list as an open-source
      alternative to Composio / Zapier (the comparison table on the homepage
      maps directly to these listings).

## 4. Launch posts (timed — referral spikes + backlinks)

Do these once the docs + a couple of tutorials are polished. Each drives a traffic
spike and (if it lands) durable backlinks.

- [ ] **Show HN: "ToolsConnector – one open-source Python interface to 74 APIs for AI agents"**
      — Tuesday–Thursday, ~9am ET. Lead with the problem (fragmented SDKs), the
      primitive-not-platform angle, and a 6-line code sample. Be in the thread to answer.
- [ ] **r/Python** ("I built…" — show, don't sell), **r/LocalLLaMA** and **r/LLMDevs**
      (the MCP / agent-tooling angle), **r/SideProject**.
- [ ] **dev.to / Hashnode** — cross-post the best tutorial (canonical link back to
      the site to avoid duplicate-content dilution).
- [ ] **X / LinkedIn** — a thread: "Connecting an AI agent to Gmail/Slack/Stripe
      used to mean 3 SDKs. Here's one line each." with the comparison table image.
- [ ] **Product Hunt** — optional; works better with a video/GIF demo of the playground.

## 5. Content cadence (ongoing — the compounding SEO engine)

Long-tail, task-intent articles capture searches the catalog pages can't. Target
real queries developers type. One per week compounds fast. Suggested first batch
(each links back to the relevant connector page + docs):

- [ ] "How to send a Slack message in Python (2026)" → `slack`
- [ ] "Stripe Python integration: create customers, charges & subscriptions" → `stripe`
- [ ] "Build an MCP server for Notion in 5 minutes" → `notion` + MCP guide
- [ ] "Gmail API in Python: read, send, and label emails" → `gmail`
- [ ] "Give your OpenAI function-calling agent real tools" → framework guide
- [ ] "GitHub automation in Python: issues, PRs, releases" → `github`

Each article: 800–1500 words, a runnable code block (with the copy button),
a "Common errors" section (captures error-message searches), and an internal link
to the connector page. Publish on the site under a `/guides/` or `/blog/` path so
they're in the sitemap.

## 6. Measure (15 min setup, then monthly)

- [ ] **Google Search Console** — already verified (`googled41662209b56d435.html`).
      Submit the sitemap; check Coverage + the top queries monthly. Let it tell you
      which connector pages are getting impressions → write tutorials for those.
- [ ] **PyPI download stats** — pypistats.org/packages/toolsconnector or the BigQuery
      dataset. Track the trend, not the absolute.
- [ ] **GitHub stars over time** — star-history.com; put the chart in the README once
      it's climbing (social proof flywheel).
- [ ] **Plausible / GoatCounter** (privacy-friendly, no cookie banner needed) — if you
      want homepage traffic numbers without GA's overhead.

---

## Positioning cheat-sheet (use consistently everywhere)

One message, repeated across PyPI / GitHub / posts / site, ranks and converts better
than five clever ones:

> **ToolsConnector — one open-source Python interface to 74 APIs, for AI agents and apps.**
> A *primitive, not a platform*: runs in your process, BYOK, no vendor lock-in.
> Works with OpenAI function calling, Anthropic tool use, Gemini, and MCP.

Differentiators to hammer (these are the comparison-table rows):
- **Open source + self-hosted** (vs Composio/Zapier's hosted lock-in)
- **Dual-use** — same library for AI agents *and* plain Python apps
- **AI-native** — one method exports MCP / OpenAI / Anthropic / Gemini schemas
- **Honest quality tiers** — live-verified connectors carry a green check (trust signal)

---

*Maintainer-facing doc. Not shipped in the package. Update as channels prove out.*
