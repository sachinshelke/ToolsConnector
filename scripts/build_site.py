#!/usr/bin/env python3
"""Build the static documentation site.

Reads all connector specs, README.md files, and docs markdown,
then bundles everything into site/data.json for the SPA to render.

Usage:
    python scripts/build_site.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "webapp"))

from toolsconnector.serve import list_connectors
from toolsconnector.codegen import extract_spec

# Try to import tool_metadata for logos/colors/links
try:
    from tool_metadata import get_tool_meta, get_tool_repos
except ImportError:
    def get_tool_meta(name: str) -> dict:
        return {"color": "#6366f1", "logo": "", "company": "", "website": "", "docs": ""}
    def get_tool_repos(name: str) -> list[dict[str, str]]:
        return []

SITE_DIR = ROOT / "site"
CONNECTORS_DIR = ROOT / "src" / "toolsconnector" / "connectors"
DOCS_DIR = ROOT / "docs"


# ---------------------------------------------------------------------------
# Action markdown generation (injected into README.md)
# ---------------------------------------------------------------------------

def _example_value(p: dict) -> str:
    """Generate a realistic example value for a parameter."""
    ptype = p.get("type", "string")
    pname = p.get("name", "value")
    if p.get("default") is not None:
        v = p["default"]
        if isinstance(v, str):
            return f'"{v}"'
        if isinstance(v, bool):
            return "True" if v else "False"
        return str(v)
    if ptype == "boolean":
        return "True"
    if ptype in ("integer", "number"):
        return "10"
    examples = {
        "query": '"is:unread"', "q": '"search term"',
        "email": '"user@example.com"', "to": '"recipient@example.com"',
        "subject": '"Hello"', "body": '"Hello!"',
        "channel": '"general"', "channel_id": '"C01234567"',
        "repo": '"owner/repo"', "owner": '"owner"',
        "title": '"My Title"', "name": '"my-name"',
        "status": '"active"', "state": '"open"',
        "key": '"my-key"', "value": '"my-value"',
        "message": '"Hello!"', "text": '"Hello!"',
        "url": '"https://example.com"', "path": '"/path/to/file"',
        "bucket": '"my-bucket"', "collection": '"my-collection"',
        "user_id": '"user-123"', "ticket_id": '"ticket-123"',
        "page_id": '"page-123"', "calendar_id": '"primary"',
        "list_id": '"list-123"', "task_id": '"task-123"',
    }
    return examples.get(pname, f'"your-{pname}"')


def generate_action_markdown(actions: dict, connector_name: str) -> str:
    """Generate markdown documentation for all actions."""
    lines = []
    for aname in sorted(actions.keys()):
        act = actions[aname]
        params = act.get("parameters", [])
        dangerous = act.get("dangerous", False)
        return_type = act.get("return_type", "Any")

        warn = " :warning:" if dangerous else ""
        lines.append(f"\n### `{aname}`{warn}\n")
        lines.append(f"{act.get('description', '')}\n")

        if params:
            lines.append("| Parameter | Type | Required | Description |")
            lines.append("|---|---|---|---|")
            for p in params:
                req = "Yes" if p.get("required") else "No"
                default = f" (default: `{p['default']}`)" if p.get("default") is not None else ""
                lines.append(f"| `{p['name']}` | `{p.get('type', 'any')}` | {req} | {p.get('description', '')}{default} |")
            lines.append("")

        lines.append(f"**Returns:** `{return_type}`\n")

        # Example code
        req_params = [p for p in params if p.get("required")]
        opt_params = [p for p in params if not p.get("required")]
        ex_params = req_params + opt_params[:2]
        if ex_params:
            args = ", ".join(f'"{p["name"]}": {_example_value(p)}' for p in ex_params)
            lines.append(f'```python\nresult = kit.execute("{connector_name}_{aname}", {{{args}}})\n```\n')
        else:
            lines.append(f'```python\nresult = kit.execute("{connector_name}_{aname}", {{}})\n```\n')

        lines.append("---\n")

    return "\n".join(lines)


def _badge_escape(text: str) -> str:
    """Escape text for use in shields.io badge URLs."""
    return text.replace("-", "--").replace("_", "__").replace(" ", "_")


def _badge_color(category: str) -> str:
    """Return a shields.io color for a category."""
    colors = {
        "communication": "3B82F6", "crm": "F59E0B", "project_management": "8B5CF6",
        "code_platform": "1E293B", "devops": "06B6D4", "database": "10B981",
        "productivity": "F97316", "ai_ml": "7C3AED", "finance": "6366F1",
        "marketing": "EC4899", "storage": "14B8A6", "message_queue": "EF4444",
        "analytics": "8B5CF6", "security": "059669", "knowledge": "0EA5E9",
        "ecommerce": "84CC16", "custom": "6366F1",
    }
    return colors.get(category, "6366F1")


def inject_actions_into_readme(readme: str, action_md: str) -> str:
    """Replace content between ACTIONS_START and ACTIONS_END markers."""
    if "<!-- ACTIONS_START -->" in readme:
        # re.sub interprets backslashes in replacement; escape them
        safe_replacement = f"<!-- ACTIONS_START -->\n{action_md}\n<!-- ACTIONS_END -->"
        return re.sub(
            r"<!-- ACTIONS_START -->.*?<!-- ACTIONS_END -->",
            safe_replacement.replace("\\", "\\\\"),
            readme,
            flags=re.DOTALL,
        )
    # Fallback: append
    return readme + f"\n\n## Actions\n\n{action_md}"


# ---------------------------------------------------------------------------
# Connector README resolution
# ---------------------------------------------------------------------------

def find_readme(name: str) -> Path | None:
    """Find the README.md for a connector, checking alternate directory names."""
    candidates = [
        CONNECTORS_DIR / name / "README.md",
        CONNECTORS_DIR / f"{name}_connector" / "README.md",
        CONNECTORS_DIR / name.replace("_connector", "") / "README.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Docs collection
# ---------------------------------------------------------------------------

DOCS_MAP = {
    # Getting Started
    "introduction": ("Introduction", "README.md"),
    "quickstart": ("Quick Start", "guides/quickstart.md"),
    "installation": ("Installation", "guides/installation.md"),
    "credentials": ("Credentials & Auth", "guides/credentials.md"),
    # Using ToolsConnector
    "mcp-server": ("MCP Server", "guides/mcp-server.md"),
    "ai-frameworks": ("AI Frameworks", "guides/ai-frameworks.md"),
    "resilience": ("Resilience & Error Handling", "guides/resilience.md"),
    "cli": ("CLI Reference", "guides/cli.md"),
    # Connectors
    "connectors-overview": ("All Connectors", "connectors/README.md"),
    "connectors-communication": ("Communication", "connectors/communication.md"),
    "connectors-code-platforms": ("Code Platforms", "connectors/code-platforms.md"),
    "connectors-project-management": ("Project Management", "connectors/project-management.md"),
    "connectors-crm": ("CRM & Support", "connectors/crm.md"),
    "connectors-database": ("Database", "connectors/database.md"),
    "connectors-devops": ("DevOps & Cloud", "connectors/devops.md"),
    "connectors-ai-ml": ("AI/ML", "connectors/ai-ml.md"),
    "connectors-finance": ("Finance & Payments", "connectors/finance.md"),
    "connectors-storage": ("Storage", "connectors/storage.md"),
    # Reference
    "api": ("API Reference", "API.md"),
    "architecture-faq": ("Architecture FAQ", "ARCHITECTURE_FAQ.md"),
    "adding-connector": ("Adding a Connector", "guides/adding-connector.md"),
}


def collect_docs() -> dict:
    """Read all documentation markdown files."""
    docs = {}
    for doc_id, (title, rel_path) in DOCS_MAP.items():
        filepath = DOCS_DIR / rel_path
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            docs[doc_id] = {"title": title, "content": content}
        else:
            print(f"  WARN  docs/{rel_path} not found, skipping")
    return docs


# ---------------------------------------------------------------------------
# System prompt for AI assistant
# ---------------------------------------------------------------------------

def build_system_prompt(names: list[str], specs: dict, cats: set) -> str:
    """Build the AI assistant system prompt from live project data."""
    cl = ", ".join(f"{specs[n]['display_name']} ({n})" for n in names)
    total_actions = sum(len(s.get("actions", {})) for s in specs.values())
    cat_list = ", ".join(c.replace("_", " ").title() for c in sorted(cats))
    return (
        "You are the ToolsConnector AI assistant helping developers.\n\n"
        "## What is ToolsConnector?\n"
        f"A universal tool-connection primitive for Python. {len(names)} connectors, "
        f"{total_actions} actions across {len(cats)} categories. A primitive, not a platform.\n\n"
        f"## Connectors ({len(names)})\n{cl}\n\n"
        f"## Categories: {cat_list}\n\n"
        "## How ToolKit Works\n"
        "```python\n"
        "from toolsconnector.serve import ToolKit\n"
        'kit = ToolKit(["gmail", "slack"], credentials={"gmail": "tok", "slack": "tok"})\n'
        "tools = kit.to_openai_tools()      # OpenAI\n"
        "tools = kit.to_anthropic_tools()   # Anthropic\n"
        "tools = kit.to_gemini_tools()      # Gemini\n"
        'result = await kit.aexecute("gmail_list_emails", {"query": "is:unread"})\n'
        "kit.serve_mcp()  # MCP server\n"
        "```\n\n"
        "## Install\n"
        '`pip install toolsconnector` or `pip install "toolsconnector[gmail,slack]"`\n\n'
        "## Key Features\n"
        f"{len(names)} connectors, {total_actions} actions, {len(cats)} categories. "
        "OpenAI/Anthropic/Gemini schemas. MCP server. Circuit breakers, retries, timeouts. "
        "Async-first + sync wrappers. JSON Schema validation. Multi-tenant. BYOK auth.\n\n"
        "Be concise, technical, include code examples."
    )


# ---------------------------------------------------------------------------
# Static connector page generator  (one HTML file per connector for SEO)
# ---------------------------------------------------------------------------

CATEGORY_LABELS_PY: dict[str, str] = {
    "communication": "Communication", "database": "Database", "devops": "DevOps",
    "crm": "CRM & Support", "project_management": "Project Management",
    "ai_ml": "AI / ML", "productivity": "Productivity", "security": "Security",
    "knowledge": "Knowledge", "storage": "Storage", "code_platform": "Code Platform",
    "marketing": "Marketing", "analytics": "Analytics", "finance": "Finance",
    "message_queue": "Message Queue", "ecommerce": "E-Commerce", "custom": "Custom",
}

CATEGORY_COLORS_PY: dict[str, str] = {
    "communication": "#3B82F6", "database": "#10B981", "devops": "#06B6D4",
    "crm": "#F59E0B", "project_management": "#8B5CF6", "ai_ml": "#7C3AED",
    "productivity": "#F97316", "security": "#059669", "knowledge": "#0EA5E9",
    "storage": "#14B8A6", "code_platform": "#1E293B", "marketing": "#EC4899",
    "analytics": "#8B5CF6", "finance": "#6366F1", "message_queue": "#EF4444",
    "ecommerce": "#84CC16", "custom": "#6366F1",
}


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def generate_connector_page(name: str, data: dict) -> str:
    """Return a fully static, SEO-rich HTML page for one connector."""
    display_name = data["display_name"]
    description  = data.get("description", "")
    category_key = data.get("category", "")
    category     = CATEGORY_LABELS_PY.get(category_key, category_key.replace("_", " ").title())
    cat_color    = CATEGORY_COLORS_PY.get(category_key, "#6366F1")
    actions      = data.get("actions", {})
    n_actions    = len(actions)
    meta         = data.get("meta", {})
    logo_url     = meta.get("logo", "")
    install_pkg  = name.replace("_connector", "")

    page_title = f"{display_name} Python Connector — {n_actions} Actions | ToolsConnector"
    page_desc  = (
        f"Connect {display_name} to Python apps and AI agents with {n_actions} typed actions. "
        f"Supports OpenAI function calling, Anthropic tool use, MCP server, and Google Gemini. "
        f'Install: pip install "toolsconnector[{install_pkg}]". Apache 2.0. Free.'
    )
    keywords = ", ".join([
        f"{display_name} Python", f"{display_name} API Python", f"{display_name} connector Python",
        "OpenAI function calling", "Anthropic tool use", "MCP server Python",
        "AI agent tools Python", "ToolsConnector",
    ])

    # ── JSON-LD ──────────────────────────────────────────────────────────────
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": f"ToolsConnector — {display_name} Connector",
        "description": page_desc,
        "url": f"https://toolsconnector.github.io/connectors/{name}/",
        "downloadUrl": "https://pypi.org/project/toolsconnector/",
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "Any",
        "programmingLanguage": "Python",
        "license": "https://opensource.org/licenses/Apache-2.0",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "featureList": [a for a in sorted(actions.keys())],
        "author": {
            "@type": "Organization",
            "name": "ToolsConnector",
            "url": "https://toolsconnector.github.io/",
        },
    }, indent=2)

    # ── Action rows ──────────────────────────────────────────────────────────
    action_rows: list[str] = []
    for aname in sorted(actions.keys()):
        act   = actions[aname]
        params = act.get("parameters", [])
        desc  = _esc(act.get("description", ""))
        rtype = _esc(act.get("return_type", "Any"))
        danger = " ⚠" if act.get("dangerous") else ""
        req   = [_esc(p["name"]) for p in params if p.get("required")]
        opt   = [_esc(p["name"]) for p in params if not p.get("required")]
        param_bits: list[str] = []
        if req:
            param_bits.append(f'<span class="req">{", ".join(req)}</span>')
        if opt:
            param_bits.append(f'<span class="opt">[{", ".join(opt)}]</span>')
        param_html = " &nbsp;".join(param_bits) if param_bits else '<span class="opt">—</span>'
        action_rows.append(
            f'<tr><td><code>{_esc(aname)}{danger}</code></td>'
            f'<td class="desc">{desc}</td>'
            f'<td>{param_html}</td>'
            f'<td><code>{rtype}</code></td></tr>'
        )
    table_body = "\n".join(action_rows)

    # ── Logo img ─────────────────────────────────────────────────────────────
    logo_html = (
        f'<img src="{_esc(logo_url)}" alt="{_esc(display_name)}" '
        f'width="56" height="56" style="border-radius:14px;object-fit:contain;'
        f'background:#f8fafc;padding:4px">'
        if logo_url else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(page_title)}</title>
<meta name="description" content="{_esc(page_desc)}">
<meta name="keywords" content="{_esc(keywords)}">
<meta name="author" content="ToolsConnector">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" href="https://toolsconnector.github.io/connectors/{name}/">
<link rel="icon" type="image/svg+xml" href="/logo.svg">
<meta name="theme-color" content="#2563eb">

<meta property="og:type" content="website">
<meta property="og:url" content="https://toolsconnector.github.io/connectors/{name}/">
<meta property="og:site_name" content="ToolsConnector">
<meta property="og:title" content="{_esc(page_title)}">
<meta property="og:description" content="{_esc(page_desc)}">
<meta property="og:image" content="https://toolsconnector.github.io/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@toolsconnector">
<meta name="twitter:title" content="{_esc(page_title)}">
<meta name="twitter:description" content="{_esc(page_desc)}">
<meta name="twitter:image" content="https://toolsconnector.github.io/og-image.png">

<script type="application/ld+json">
{jsonld}
</script>

<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, -apple-system, sans-serif; color: #0f172a; background: #fff; line-height: 1.6; }}
a {{ color: #2563eb; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
code {{ font-family: ui-monospace, monospace; font-size: .875em; background: #f1f5f9;
        padding: .15em .4em; border-radius: 4px; }}

/* ── Nav ── */
nav {{ border-bottom: 1px solid #e2e8f0; padding: .75rem 1.5rem;
      display: flex; align-items: center; gap: .75rem; }}
.nav-logo {{ font-weight: 800; font-size: 1.1rem; color: #0f172a; display:flex; align-items:center; gap:.5rem; }}
nav a.btn {{ margin-left: auto; background: #2563eb; color: #fff; padding: .45rem 1.1rem;
             border-radius: 8px; font-size: .875rem; font-weight: 600; }}
nav a.btn:hover {{ background: #1d4ed8; text-decoration: none; }}

/* ── Hero ── */
.hero {{ max-width: 860px; margin: 3rem auto 2rem; padding: 0 1.5rem; }}
.hero-top {{ display: flex; align-items: center; gap: 1.25rem; margin-bottom: 1rem; }}
.badge {{ display:inline-flex; align-items:center; padding:.25rem .75rem; border-radius:20px;
          font-size:.75rem; font-weight:600; color:#fff; background:{cat_color}; }}
h1 {{ font-size: clamp(1.6rem, 4vw, 2.25rem); font-weight: 800; margin-bottom: .5rem; }}
.desc {{ font-size: 1.05rem; color: #475569; max-width: 700px; margin-bottom: 1.5rem; }}
.install-box {{ background: #0f172a; color: #e2e8f0; border-radius: 10px;
               padding: .9rem 1.25rem; font-family: ui-monospace, monospace;
               font-size: .875rem; display:inline-block; margin-bottom:1.5rem; }}
.install-box .dollar {{ color: #22c55e; margin-right:.5rem; }}
.install-box .pkg {{ color: #f97316; }}

/* ── Stats strip ── */
.stats {{ display: flex; gap: 2rem; margin-bottom: 2rem; flex-wrap: wrap; }}
.stat {{ text-align: center; }}
.stat-num {{ font-size: 1.75rem; font-weight: 800; color: #2563eb; }}
.stat-lbl {{ font-size: .7rem; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing:.05em; }}

/* ── Actions table ── */
.section {{ max-width: 1100px; margin: 0 auto 3rem; padding: 0 1.5rem; }}
.section h2 {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 1rem; padding-bottom: .5rem;
               border-bottom: 2px solid #e2e8f0; }}
.tbl-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: .875rem; }}
th {{ text-align: left; padding: .6rem .75rem; background: #f8fafc; color: #64748b;
      font-weight: 600; font-size: .75rem; text-transform: uppercase; letter-spacing:.05em;
      border-bottom: 1px solid #e2e8f0; }}
td {{ padding: .6rem .75rem; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
tr:last-child td {{ border-bottom: none; }}
td.desc {{ color: #475569; max-width: 380px; }}
.req {{ color: #dc2626; }}
.opt {{ color: #94a3b8; }}

/* ── CTA ── */
.cta {{ text-align: center; padding: 2rem 1.5rem; border-top: 1px solid #e2e8f0; margin-top: 1rem; }}
.cta a {{ display: inline-flex; align-items: center; gap: .5rem; background: #2563eb; color: #fff;
          padding: .7rem 1.75rem; border-radius: 10px; font-weight: 700; font-size: 1rem; }}
.cta a:hover {{ background: #1d4ed8; text-decoration: none; }}
.cta p {{ margin-top: .75rem; color: #94a3b8; font-size: .875rem; }}

/* ── Footer ── */
footer {{ border-top: 1px solid #e2e8f0; padding: 1.25rem 1.5rem; text-align:center;
          color: #94a3b8; font-size: .8rem; }}
footer a {{ color: #94a3b8; }}

@media (max-width: 600px) {{
  .stats {{ gap: 1rem; }} .stat-num {{ font-size: 1.4rem; }}
  th:nth-child(3), td:nth-child(3) {{ display: none; }}
}}
</style>
</head>
<body>

<nav>
  <a href="https://toolsconnector.github.io/" class="nav-logo">
    <img src="/logo.svg" alt="" width="28" height="28">
    ToolsConnector
  </a>
  <a href="https://toolsconnector.github.io/#/connectors" style="color:#64748b;font-size:.875rem">← All Connectors</a>
  <a href="https://toolsconnector.github.io/#/connector/{name}" class="btn">Open Interactive Docs →</a>
</nav>

<div class="hero">
  <div class="hero-top">
    {logo_html}
    <div>
      <span class="badge">{_esc(category)}</span>
      <h1>{_esc(display_name)} Connector</h1>
    </div>
  </div>
  <p class="desc">{_esc(description)}</p>

  <div class="install-box">
    <span class="dollar">$</span>pip install <span class="pkg">"toolsconnector[{_esc(install_pkg)}]"</span>
  </div>

  <div class="stats">
    <div class="stat">
      <div class="stat-num">{n_actions}</div>
      <div class="stat-lbl">Actions</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:#8b5cf6">{category}</div>
      <div class="stat-lbl">Category</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:#10b981">Free</div>
      <div class="stat-lbl">Apache 2.0</div>
    </div>
  </div>
</div>

<div class="section">
  <h2>All {n_actions} Actions</h2>
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th>Action</th>
          <th>Description</th>
          <th>Parameters</th>
          <th>Returns</th>
        </tr>
      </thead>
      <tbody>
        {table_body}
      </tbody>
    </table>
  </div>
</div>

<div class="cta">
  <a href="https://toolsconnector.github.io/#/connector/{name}">
    Open Interactive Docs &amp; Playground →
  </a>
  <p>Full schema explorer, code generation, and live API testing</p>
</div>

<footer>
  <a href="https://toolsconnector.github.io/">ToolsConnector</a> ·
  <a href="https://github.com/ToolsConnector/ToolsConnector">GitHub</a> ·
  <a href="https://pypi.org/project/toolsconnector/">PyPI</a> ·
  <a href="https://opensource.org/licenses/Apache-2.0">Apache 2.0</a>
</footer>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Sitemap generator  (proper /connectors/{name}/ URLs, not hash routes)
# ---------------------------------------------------------------------------

def generate_sitemap(connector_names: list[str], doc_keys: list[str]) -> str:
    """Return a sitemap.xml with only real, crawlable URLs (no # fragments).

    Hash-based SPA routes (#/connectors, #/docs/...) are invalid in sitemaps —
    Google rejects the entire file if any <loc> contains a fragment identifier.
    Only the homepage and the pre-generated static connector pages are included.
    """
    base = "https://toolsconnector.github.io"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "",
        "  <!-- Homepage -->",
        "  <url>",
        f"    <loc>{base}/</loc>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
        "",
        "  <!-- Static connector pages (53 individually crawlable URLs) -->",
    ]
    for cname in sorted(connector_names):
        lines += [
            "  <url>",
            f"    <loc>{base}/connectors/{cname}/</loc>",
            "    <changefreq>monthly</changefreq>",
            "    <priority>0.8</priority>",
            "  </url>",
        ]

    lines += ["", "</urlset>", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main():
    print("Building static site...\n")

    names = sorted(list_connectors())
    connectors_out = {}
    total_actions = 0

    # ── Connectors ──────────────────────────────────────────────────
    for name in names:
        try:
            sp = extract_spec(name)
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            continue

        actions = sp.get("actions", {})
        total_actions += len(actions)
        meta = get_tool_meta(name)

        # Read and process README
        readme_path = find_readme(name)
        readme_md = ""
        if readme_path:
            readme_md = readme_path.read_text(encoding="utf-8")
            action_md = generate_action_markdown(actions, name)
            readme_md = inject_actions_into_readme(readme_md, action_md)

            # Inject logo before the h1
            logo_url = meta.get("logo", "")
            if logo_url and readme_md.startswith("# "):
                logo_line = f'<img src="{logo_url}" alt="{sp["display_name"]}" width="48" height="48" style="border-radius:12px">\n\n'
                readme_md = logo_line + readme_md

            # Inject shields.io badges after the blockquote tagline
            category = sp.get("category", "").replace("_", " ").title()
            protocol = sp.get("protocol", "rest").upper()
            n_actions = len(actions)
            cat_color = _badge_color(sp.get("category", ""))
            repos = get_tool_repos(name)

            badges = []
            badges.append(f"![Category](https://img.shields.io/badge/category-{_badge_escape(category)}-{cat_color})")
            badges.append(f"![Protocol](https://img.shields.io/badge/protocol-{protocol}-blue)")
            badges.append(f"![Actions](https://img.shields.io/badge/actions-{n_actions}-purple)")

            # GitHub stars badge for the primary (Python) repo
            for repo in repos:
                gh_parts = repo["url"].rstrip("/").replace("https://github.com/", "").split("/")
                if len(gh_parts) >= 2:
                    gh_slug = "/".join(gh_parts[:2])
                    badges.append(f"[![GitHub stars](https://img.shields.io/github/stars/{gh_slug}?style=social)]({repo['url']})")
                    break  # Only one stars badge

            # SDK repo badges (multi-language) — append to same badges list
            if repos:
                for repo in repos:
                    lang = repo["lang"]
                    lang_colors = {
                        "Python": "3776AB", "Node": "339933", "TypeScript": "3178C6",
                        "Go": "00ADD8", "Java": "ED8B00", "Ruby": "CC342D",
                        "CLI": "4D4D4D", "Erlang": "A90533", "C++": "00599C",
                    }
                    lc = "6366F1"
                    for k, v in lang_colors.items():
                        if k in lang:
                            lc = v
                            break
                    lang_esc = _badge_escape(lang)
                    badges.append(f"[![{lang}](https://img.shields.io/badge/{lang_esc}-SDK-{lc}?logo=github)]({repo['url']})")

            # All badges on ONE line so markdown renders them inline with wrapping
            badge_line = " ".join(badges) + "\n\n"

            # Insert badges after the first blockquote (tagline)
            bq_end = readme_md.find("\n\n", readme_md.find("> "))
            if bq_end > 0:
                readme_md = readme_md[:bq_end + 2] + badge_line + readme_md[bq_end + 2:]

        connectors_out[name] = {
            "display_name": sp.get("display_name", name),
            "description": sp.get("description", ""),
            "category": sp.get("category", ""),
            "protocol": sp.get("protocol", "rest"),
            "actions": actions,
            "readme_md": readme_md,
            "meta": {
                "logo": meta.get("logo", ""),
                "color": meta.get("color", "#6366f1"),
                "company": meta.get("company", ""),
                "website": meta.get("website", ""),
                "docs": meta.get("docs", ""),
                "github": meta.get("github", ""),
                "tagline": meta.get("tagline", ""),
                "auth_methods": meta.get("auth_methods", []),
                "rate_limit": meta.get("rate_limit", ""),
                "pricing": meta.get("pricing", ""),
                "get_credentials_url": meta.get("get_credentials_url", ""),
                "repos": repos,
            },
        }
        act_count = len(actions)
        has_readme = "+" if readme_md else "-"
        print(f"  {has_readme} {name}: {sp['display_name']} ({act_count} actions)")

    # ── Docs ────────────────────────────────────────────────────────
    print()
    docs = collect_docs()
    print(f"  Docs: {len(docs)} pages bundled\n")

    # ── Categories ──────────────────────────────────────────────────
    cats = set(c["category"] for c in connectors_out.values())

    # ── System prompt ───────────────────────────────────────────────
    specs_for_prompt = {n: connectors_out[n] for n in connectors_out}
    system_prompt = build_system_prompt(list(connectors_out.keys()), specs_for_prompt, cats)

    # ── Assemble output ─────────────────────────────────────────────
    output = {
        "connectors": connectors_out,
        "docs": docs,
        "meta": {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "connector_count": len(connectors_out),
            "action_count": total_actions,
            "category_count": len(cats),
            "system_prompt": system_prompt,
        },
    }

    # ── Write data.json ─────────────────────────────────────────────
    SITE_DIR.mkdir(exist_ok=True)
    out_path = SITE_DIR / "data.json"
    out_path.write_text(json.dumps(output, indent=None, ensure_ascii=False), encoding="utf-8")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Output: {out_path} ({size_mb:.1f} MB)")
    print(f"Connectors: {len(connectors_out)} | Actions: {total_actions} | Docs: {len(docs)} | Categories: {len(cats)}")

    # ── Write static connector pages ────────────────────────────────
    print("\nGenerating static connector pages...")
    pages_dir = SITE_DIR / "connectors"
    pages_dir.mkdir(exist_ok=True)
    for cname, cdata in connectors_out.items():
        page_dir = pages_dir / cname
        page_dir.mkdir(exist_ok=True)
        html = generate_connector_page(cname, cdata)
        (page_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  {len(connectors_out)} connector pages → site/connectors/*/index.html")

    # ── Write sitemap.xml ───────────────────────────────────────────
    sitemap_xml = generate_sitemap(list(connectors_out.keys()), list(docs.keys()))
    (SITE_DIR / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")
    print(f"  Sitemap → site/sitemap.xml ({len(connectors_out) + len(docs) + 2} URLs)")

    print("Done.")


if __name__ == "__main__":
    main()
