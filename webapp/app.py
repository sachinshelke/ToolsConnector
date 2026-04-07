"""ToolsConnector Web Playground.

Interactive web interface for exploring connectors, testing schemas,
and chatting with an AI assistant about the project.

Usage:
    pip install flask httpx
    export OPENROUTER_API_KEY=sk-or-v1-...
    python webapp/app.py
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from collections import Counter
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from flask import Flask, render_template_string, request, jsonify, Response
import httpx
from toolsconnector.serve import ToolKit, list_connectors, get_connector_class
from toolsconnector.health import HealthChecker
from toolsconnector.codegen import extract_spec, extract_all_specs
from tool_metadata import get_tool_meta

app = Flask(__name__)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "qwen/qwen3.6-plus:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# -- Data helpers ----------------------------------------------------------
_spec_cache: dict[str, dict] = {}

def _get_spec(name: str) -> dict[str, Any]:
    if name not in _spec_cache:
        _spec_cache[name] = extract_spec(name)
    return _spec_cache[name]

def _all_specs() -> dict[str, dict]:
    for n in list_connectors():
        _get_spec(n)
    return _spec_cache

def _cat(c: str) -> str:
    return c.replace("_", " ").title()

def _stats() -> dict[str, Any]:
    specs = _all_specs()
    cats: Counter[str] = Counter()
    acts = 0
    for s in specs.values():
        cats[s["category"]] += 1
        acts += len(s.get("actions", {}))
    return {"connectors": len(specs), "actions": acts, "categories": len(cats), "by_category": dict(sorted(cats.items()))}

# -- Base template ---------------------------------------------------------
_BASE = r"""<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} - ToolsConnector</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={darkMode:'class',theme:{extend:{colors:{b:{50:'#f0f4ff',100:'#dbe4ff',200:'#bac8ff',400:'#748ffc',500:'#5c7cfa',600:'#4c6ef5',700:'#4263eb',800:'#3b5bdb',900:'#364fc7'}},fontFamily:{sans:['Inter','system-ui','sans-serif'],mono:['JetBrains Mono','monospace']}}}}</script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
body{font-family:'Inter',system-ui,sans-serif}code,pre{font-family:'JetBrains Mono',monospace}
.fi{animation:fi .3s ease-in}@keyframes fi{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.gl{backdrop-filter:blur(12px);background:rgba(255,255,255,.75)}.dark .gl{background:rgba(15,23,42,.75)}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#94a3b8;border-radius:3px}
</style></head>
<body class="bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 min-h-screen">
<nav class="gl sticky top-0 z-50 border-b border-slate-200 dark:border-slate-800">
<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
<a href="/" class="flex items-center gap-2 text-lg font-bold text-b-700 dark:text-b-400">
<svg class="w-7 h-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>ToolsConnector</a>
<div class="hidden md:flex items-center gap-1">
<a href="/" class="px-3 py-2 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-800">Home</a>
<a href="/connectors" class="px-3 py-2 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-800">Connectors</a>
<a href="/playground" class="px-3 py-2 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-800">Playground</a>
<a href="/docs" class="px-3 py-2 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-800">Docs</a>
<a href="/assistant" class="px-3 py-2 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-800">AI Assistant</a>
<a href="/health" class="px-3 py-2 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-800">Health</a></div>
<button onclick="document.documentElement.classList.toggle('dark')" class="p-2 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800">
<svg class="w-5 h-5 dark:hidden" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>
<svg class="w-5 h-5 hidden dark:block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>
</button></div></nav>
<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 fi">{{ content|safe }}</main>
<footer class="border-t border-slate-200 dark:border-slate-800 mt-16"><div class="max-w-7xl mx-auto px-4 py-8 text-center text-sm text-slate-500">ToolsConnector &mdash; The universal tool-connection primitive for AI agents and applications.</div></footer>
</body></html>"""

def _r(title: str, content: str) -> str:
    return render_template_string(_BASE, title=title, content=content)

# -- Routes ----------------------------------------------------------------
@app.route("/")
def home():
    s = _stats()
    cats = "".join(f'<a href="/connectors?cat={c}" class="group block p-5 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-b-400 hover:shadow-lg transition-all bg-white dark:bg-slate-900"><div class="text-2xl font-bold text-b-600 dark:text-b-400">{n}</div><div class="text-sm font-medium text-slate-700 dark:text-slate-300 mt-1">{_cat(c)}</div></a>' for c, n in s["by_category"].items())
    stat = lambda v, c, l: f'<div class="text-center p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm"><div class="text-3xl font-bold text-{c}">{v}</div><div class="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">{l}</div></div>'
    link = lambda href, color, icon, t, d: f'<a href="{href}" class="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-{color}-400 bg-white dark:bg-slate-900 transition-all hover:shadow-md"><div class="w-10 h-10 rounded-lg bg-{color}-100 dark:bg-{color}-900/30 flex items-center justify-center text-{color}-600 dark:text-{color}-400"><svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="{icon}"/></svg></div><div><div class="font-medium">{t}</div><div class="text-xs text-slate-500">{d}</div></div></a>'
    return _r("Home", f"""
<div class="text-center mb-12">
<h1 class="text-4xl sm:text-5xl font-bold bg-gradient-to-r from-b-600 to-purple-600 bg-clip-text text-transparent mb-4">ToolsConnector Playground</h1>
<p class="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">The universal tool-connection primitive. Browse connectors, explore schemas, and test integrations.</p></div>
<div class="grid grid-cols-3 gap-4 max-w-xl mx-auto mb-12">{stat(s['connectors'],'b-600 dark:text-b-400','Connectors')}{stat(s['actions'],'purple-600 dark:text-purple-400','Actions')}{stat(s['categories'],'emerald-600 dark:text-emerald-400','Categories')}</div>
<div class="max-w-xl mx-auto mb-12"><div class="relative"><svg class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg>
<input type="text" placeholder="Search connectors... (e.g. gmail, slack, stripe)" class="w-full pl-10 pr-4 py-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-b-500 focus:border-b-500 outline-none" onkeyup="if(event.key==='Enter')location.href='/connectors?q='+this.value"></div></div>
<h2 class="text-xl font-semibold mb-4">Categories</h2>
<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 mb-12">{cats}</div>
<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
{link('/connectors','b','M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6z','Browse All','Explore all 50 connectors')}
{link('/playground','purple','M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5','Schema Playground','Generate AI-ready schemas')}
{link('/assistant','emerald','M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z','AI Assistant','Ask anything about the project')}</div>""")


@app.route("/connectors")
def connectors_page():
    specs = _all_specs()
    q = request.args.get("q", "").lower()
    cf = request.args.get("cat", "")
    grouped: dict[str, list] = {}
    for name in sorted(specs):
        sp = specs[name]
        if q and q not in name and q not in sp.get("description", "").lower() and q not in sp.get("display_name", "").lower():
            continue
        if cf and sp["category"] != cf:
            continue
        grouped.setdefault(sp["category"], []).append((name, sp))
    html = ""
    for cat in sorted(grouped):
        items = grouped[cat]
        html += f'<h3 class="text-lg font-semibold mt-8 mb-3 text-slate-700 dark:text-slate-300">{_cat(cat)} <span class="text-sm font-normal text-slate-400">({len(items)})</span></h3><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">'
        for name, sp in items:
            na = len(sp.get("actions", {}))
            html += f'<a href="/connector/{name}" class="group block p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-b-400 bg-white dark:bg-slate-900 hover:shadow-md transition-all"><div class="flex items-start justify-between"><div><div class="font-semibold text-b-700 dark:text-b-400">{sp["display_name"]}</div><div class="text-xs text-slate-500 mt-0.5">{name}</div></div><span class="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-medium">{na} actions</span></div><p class="text-sm text-slate-600 dark:text-slate-400 mt-2 line-clamp-2">{sp.get("description","")}</p></a>'
        html += "</div>"
    return _r("Connectors", f"""
<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
<h1 class="text-2xl font-bold">Connectors</h1>
<div class="relative w-full sm:w-72"><svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg>
<input type="text" value="{q}" placeholder="Filter connectors..." class="w-full pl-9 pr-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-b-500 outline-none" onkeyup="if(event.key==='Enter')location.href='/connectors?q='+this.value+'&cat={cf}'"></div></div>
{html or '<p class="text-slate-500 py-8 text-center">No connectors match your search.</p>'}""")


def _param_row(p: dict) -> str:
    req = '<span class="inline-block px-1.5 py-0.5 text-[10px] rounded bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-semibold">REQUIRED</span>' if p.get("required") else '<span class="inline-block px-1.5 py-0.5 text-[10px] rounded bg-slate-100 dark:bg-slate-800 text-slate-400 font-medium">optional</span>'
    default = f'<span class="text-[11px] text-slate-400 ml-1">= {p["default"]}</span>' if p.get("default") is not None else ""
    type_badge = f'<span class="text-[11px] px-1.5 py-0.5 rounded bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 font-mono">{p.get("type","any")}</span>'
    return f'<tr class="border-b border-slate-100 dark:border-slate-800 last:border-0"><td class="py-2.5 pr-3 align-top"><code class="text-xs font-semibold text-b-700 dark:text-b-400">{p["name"]}</code>{default}</td><td class="py-2.5 pr-3 align-top">{type_badge}</td><td class="py-2.5 pr-3 align-top">{req}</td><td class="py-2.5 text-xs text-slate-500 dark:text-slate-400">{p.get("description","")}</td></tr>'

def _action_card(an: str, act: dict, connector_name: str) -> str:
    params = act.get("parameters", [])
    badges = ""
    if act.get("dangerous"):
        badges += '<span class="text-[10px] px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-semibold uppercase tracking-wide">Destructive</span>'
    if act.get("requires_scope"):
        badges += f'<span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 font-medium">scope: {act["requires_scope"]}</span>'
    if act.get("idempotent"):
        badges += '<span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 font-medium">idempotent</span>'

    param_sig = ", ".join(f'{p["name"]}' for p in params)
    return_type = act.get("return_type", "Any")

    param_table = ""
    if params:
        rows = "".join(_param_row(p) for p in params)
        param_table = f'''<div class="mt-4">
<h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Parameters</h4>
<table class="w-full text-sm"><thead><tr class="text-left text-[10px] font-semibold text-slate-400 uppercase tracking-wider"><th class="pb-2 pr-3">Name</th><th class="pb-2 pr-3">Type</th><th class="pb-2 pr-3">Required</th><th class="pb-2">Description</th></tr></thead><tbody>{rows}</tbody></table></div>'''

    tool_name = f"{connector_name}_{an}"
    usage = f'''<div class="mt-4 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
<div class="flex items-center justify-between mb-1"><span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Usage</span>
<button onclick="navigator.clipboard.writeText(this.parentElement.nextElementSibling.textContent.trim());this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)" class="text-[10px] px-2 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-500 hover:text-slate-700 cursor-pointer">Copy</button></div>
<code class="text-xs text-slate-600 dark:text-slate-300 font-mono block">kit.execute("{tool_name}", {{{", ".join(f'"{p["name"]}": ...' for p in params[:3])}{", ..." if len(params) > 3 else ""}}})</code></div>'''

    return f'''<div class="action-card rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden transition-all hover:shadow-md" data-action="{an}">
<div class="p-5">
<div class="flex items-start justify-between gap-3 flex-wrap">
<div><div class="flex items-center gap-2 flex-wrap">
<code class="text-sm font-bold text-slate-900 dark:text-white font-mono">{an}</code>
<span class="text-xs text-slate-400 font-mono">({param_sig}) &rarr; {return_type}</span></div>
<p class="text-sm text-slate-600 dark:text-slate-400 mt-1.5">{act.get("description","")}</p></div>
<div class="flex items-center gap-1.5 flex-shrink-0">{badges}</div></div>
{param_table}{usage}</div></div>'''

@app.route("/connector/<name>")
def connector_detail(name: str):
    try:
        sp = _get_spec(name)
    except Exception:
        return _r("Not Found", '<p class="text-center py-16 text-slate-500">Connector not found.</p>'), 404
    actions = sp.get("actions", {})
    dangerous_count = sum(1 for a in actions.values() if a.get("dangerous"))
    safe_count = len(actions) - dangerous_count
    param_count = sum(len(a.get("parameters",[])) for a in actions.values())
    meta = get_tool_meta(name)

    ahtml = "".join(_action_card(an, act, name) for an, act in sorted(actions.items()))

    install_cmd = f"pip install toolsconnector[{name}]"
    first_action = sorted(actions.keys())[0] if actions else "action"
    quick_start = f'''from toolsconnector.serve import ToolKit

kit = ToolKit(["{name}"], credentials={{"{name}": "your-token"}})
tools = kit.list_tools()
result = kit.execute("{name}_{first_action}", {{}})'''

    mcp_example = f'''from toolsconnector.serve import ToolKit
kit = ToolKit(["{name}"], credentials={{"{name}": "your-token"}})
kit.serve_mcp()  # Claude Desktop connects instantly'''

    openai_example = f'''kit = ToolKit(["{name}"], credentials={{"{name}": "your-token"}})
tools = kit.to_openai_tools()
# Pass to OpenAI: openai.chat.completions.create(tools=tools, ...)
result = kit.execute("{name}_{first_action}", {{"...": "..."}})'''

    import html as _html
    qs_escaped = _html.escape(quick_start)
    mcp_escaped = _html.escape(mcp_example)
    openai_escaped = _html.escape(openai_example)

    # Build external links
    links_html = ""
    if meta["website"]:
        links_html += f'<a href="{meta["website"]}" target="_blank" rel="noopener" class="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-sm"><svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582"/></svg>Website</a>'
    if meta["docs"]:
        links_html += f'<a href="{meta["docs"]}" target="_blank" rel="noopener" class="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-sm"><svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"/></svg>API Docs</a>'
    if meta["github"]:
        links_html += f'<a href="{meta["github"]}" target="_blank" rel="noopener" class="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-sm"><svg class="w-4 h-4 text-slate-400" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>GitHub</a>'

    # Auth methods badges
    auth_html = "".join(f'<span class="text-xs px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-medium">{m}</span>' for m in meta.get("auth_methods", []))

    # Logo
    logo_html = ""
    if meta.get("logo"):
        logo_html = f'<img src="{meta["logo"]}" alt="{sp["display_name"]}" class="w-14 h-14 rounded-xl" onerror="this.style.display=\'none\'">'
    else:
        initials = sp["display_name"][:2].upper()
        logo_html = f'<div class="w-14 h-14 rounded-xl flex items-center justify-center text-white font-bold text-lg" style="background:{meta["color"]}">{initials}</div>'

    return _r(sp["display_name"], f"""
<a href="/connectors" class="text-sm text-b-600 dark:text-b-400 hover:underline mb-6 inline-block">&larr; All Connectors</a>

<div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden mb-8">
<div class="p-6 sm:p-8" style="border-top: 4px solid {meta['color']}">
<div class="flex items-start gap-5 flex-wrap">
<div class="flex-shrink-0">{logo_html}</div>
<div class="flex-1 min-w-0">
<div class="flex items-center gap-3 flex-wrap">
<h1 class="text-3xl font-bold text-slate-900 dark:text-white">{sp["display_name"]}</h1>
{f'<span class="text-sm text-slate-400">by {meta["company"]}</span>' if meta.get("company") else ""}
</div>
<p class="text-base text-slate-600 dark:text-slate-400 mt-1.5">{meta.get("tagline") or sp.get("description","")}</p>
<div class="flex items-center gap-2 flex-wrap mt-3">
<span class="text-xs px-3 py-1 rounded-full font-semibold text-white" style="background:{meta['color']}">{_cat(sp["category"])}</span>
<span class="text-xs px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-medium">{sp.get("protocol","rest").upper()}</span>
{f'<span class="text-xs px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 font-mono">{sp.get("base_url","")}</span>' if sp.get("base_url") else ""}
</div></div>
<div class="flex items-center gap-2 flex-shrink-0 flex-wrap">{links_html}</div>
</div></div>

<div class="border-t border-slate-200 dark:border-slate-800 grid grid-cols-2 sm:grid-cols-4 divide-x divide-slate-200 dark:divide-slate-800">
<div class="text-center p-4"><div class="text-2xl font-bold text-b-600 dark:text-b-400">{len(actions)}</div><div class="text-[11px] text-slate-500 mt-0.5 uppercase tracking-wider">Actions</div></div>
<div class="text-center p-4"><div class="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{safe_count}</div><div class="text-[11px] text-slate-500 mt-0.5 uppercase tracking-wider">Safe</div></div>
<div class="text-center p-4"><div class="text-2xl font-bold text-red-500">{dangerous_count}</div><div class="text-[11px] text-slate-500 mt-0.5 uppercase tracking-wider">Destructive</div></div>
<div class="text-center p-4"><div class="text-2xl font-bold text-purple-600 dark:text-purple-400">{param_count}</div><div class="text-[11px] text-slate-500 mt-0.5 uppercase tracking-wider">Parameters</div></div>
</div></div>

<div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
<div class="p-5 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
<h3 class="text-sm font-semibold uppercase tracking-wider text-slate-500">Details</h3></div>
<div class="p-5 space-y-3 text-sm">
<div class="flex justify-between"><span class="text-slate-500">Authentication</span><div class="flex gap-1.5 flex-wrap justify-end">{auth_html or '<span class="text-slate-400">Bearer Token</span>'}</div></div>
{f'<div class="flex justify-between"><span class="text-slate-500">Pricing</span><span class="text-slate-700 dark:text-slate-300 text-right">{meta["pricing"]}</span></div>' if meta.get("pricing") else ""}
{f'<div class="flex justify-between"><span class="text-slate-500">Rate Limit</span><span class="text-slate-700 dark:text-slate-300 font-mono text-xs">{meta["rate_limit"]}</span></div>' if meta.get("rate_limit") else ""}
<div class="flex justify-between"><span class="text-slate-500">Protocol</span><span class="text-slate-700 dark:text-slate-300">{sp.get("protocol","rest").upper()}</span></div>
<div class="flex justify-between"><span class="text-slate-500">Install</span><div class="flex items-center gap-1.5"><code class="text-xs font-mono bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded">{install_cmd}</code><button onclick="navigator.clipboard.writeText('{install_cmd}');this.textContent='OK';setTimeout(()=>this.textContent='Copy',1200)" class="text-[10px] px-1.5 py-0.5 rounded bg-b-100 dark:bg-b-900/30 text-b-600 cursor-pointer">Copy</button></div></div>
</div></div>

<div class="lg:col-span-2 space-y-4">
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
<div class="flex items-center border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
<button onclick="document.querySelectorAll('.code-tab').forEach(t=>t.classList.add('hidden'));document.getElementById('tab-python').classList.remove('hidden');document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('text-b-600','border-b-600'));this.classList.add('text-b-600','border-b-600')" class="tab-btn px-4 py-3 text-sm font-medium border-b-2 text-b-600 border-b-600">Python</button>
<button onclick="document.querySelectorAll('.code-tab').forEach(t=>t.classList.add('hidden'));document.getElementById('tab-mcp').classList.remove('hidden');document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('text-b-600','border-b-600'));this.classList.add('text-b-600','border-b-600')" class="tab-btn px-4 py-3 text-sm font-medium border-b-2 border-transparent text-slate-500 hover:text-slate-700">MCP Server</button>
<button onclick="document.querySelectorAll('.code-tab').forEach(t=>t.classList.add('hidden'));document.getElementById('tab-openai').classList.remove('hidden');document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('text-b-600','border-b-600'));this.classList.add('text-b-600','border-b-600')" class="tab-btn px-4 py-3 text-sm font-medium border-b-2 border-transparent text-slate-500 hover:text-slate-700">OpenAI</button>
</div>
<div id="tab-python" class="code-tab"><pre class="text-xs bg-slate-900 text-slate-100 p-4 overflow-x-auto"><code class="language-python">{qs_escaped}</code></pre></div>
<div id="tab-mcp" class="code-tab hidden"><pre class="text-xs bg-slate-900 text-slate-100 p-4 overflow-x-auto"><code class="language-python">{mcp_escaped}</code></pre></div>
<div id="tab-openai" class="code-tab hidden"><pre class="text-xs bg-slate-900 text-slate-100 p-4 overflow-x-auto"><code class="language-python">{openai_escaped}</code></pre></div>
</div></div></div>

<div class="flex items-center justify-between mb-4 flex-wrap gap-3">
<h2 class="text-xl font-semibold">Actions</h2>
<div class="relative"><svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg>
<input type="text" placeholder="Filter actions..." class="pl-9 pr-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-b-500 outline-none w-56" oninput="document.querySelectorAll('.action-card').forEach(c=>c.style.display=c.dataset.action.includes(this.value.toLowerCase())?'':'none')"></div></div>
<div class="space-y-4">{ahtml}</div>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<script>document.querySelectorAll('pre code').forEach(b=>hljs.highlightElement(b));</script>""")


@app.route("/playground")
def playground():
    specs = _all_specs()
    cbs = "".join(f'<label class="flex items-center gap-2 text-sm cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800 px-2 py-1 rounded"><input type="checkbox" name="c" value="{n}" class="ccb rounded border-slate-300 text-b-600 focus:ring-b-500"><span>{specs[n]["display_name"]}</span></label>' for n in sorted(specs))
    return _r("Playground", """
<h1 class="text-2xl font-bold mb-6">Schema Playground</h1>
<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
<div class="lg:col-span-1 space-y-4">
<div class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
<h3 class="font-semibold mb-3">Select Connectors</h3>
<div class="flex gap-2 mb-2"><button onclick="document.querySelectorAll('.ccb').forEach(c=>c.checked=true)" class="text-xs px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-200">Select All</button><button onclick="document.querySelectorAll('.ccb').forEach(c=>c.checked=false)" class="text-xs px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-200">Clear</button></div>
<div class="relative mb-2"><svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg>
<input type="text" placeholder="Search connectors..." class="w-full pl-8 pr-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs focus:ring-2 focus:ring-b-500 outline-none" oninput="document.querySelectorAll('.ccb-wrap').forEach(w=>w.style.display=w.textContent.toLowerCase().includes(this.value.toLowerCase())?'':'none')"></div>
<div class="max-h-64 overflow-y-auto space-y-0.5">""" + cbs.replace('label class="flex', 'label class="ccb-wrap flex') + """</div></div>
<div class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 space-y-3">
<h3 class="font-semibold mb-2">Options</h3>
<div><label class="text-sm font-medium">Framework</label>
<select id="fw" class="mt-1 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm py-2 px-3 focus:ring-2 focus:ring-b-500 outline-none">
<option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option></select></div>
<label class="flex items-center gap-2 text-sm cursor-pointer"><input type="checkbox" id="exD" class="rounded border-slate-300 text-b-600 focus:ring-b-500"><span>Exclude dangerous actions</span></label>
<button onclick="genSchema()" class="w-full py-2.5 rounded-lg bg-b-600 hover:bg-b-700 text-white font-medium text-sm">Generate Schema</button></div></div>
<div class="lg:col-span-2"><div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
<div class="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
<span class="text-sm font-medium" id="si">Select connectors and click Generate</span>
<button onclick="navigator.clipboard.writeText(document.getElementById('so').textContent).then(()=>{this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)})" class="text-xs px-3 py-1 rounded bg-b-100 dark:bg-b-900/30 text-b-700 dark:text-b-400 hover:bg-b-200 font-medium">Copy</button></div>
<pre id="so" class="p-4 text-xs overflow-auto max-h-[70vh] text-slate-700 dark:text-slate-300 whitespace-pre-wrap"></pre></div></div></div>
<script>
async function genSchema(){
const cs=[...document.querySelectorAll('.ccb:checked')].map(c=>c.value);
if(!cs.length){alert('Select at least one connector.');return}
const fw=document.getElementById('fw').value,exD=document.getElementById('exD').checked;
document.getElementById('so').textContent='Generating...';
try{const r=await fetch('/api/schema',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({connectors:cs,framework:fw,exclude_dangerous:exD})});
const d=await r.json();document.getElementById('so').textContent=JSON.stringify(d.schema,null,2);
document.getElementById('si').textContent=d.tools_count+' tools generated for '+fw.charAt(0).toUpperCase()+fw.slice(1)}catch(e){document.getElementById('so').textContent='Error: '+e.message}}
</script>""")


@app.route("/api/schema", methods=["POST"])
def api_schema():
    d = request.get_json(force=True)
    cs = d.get("connectors", [])
    fw = d.get("framework", "openai")
    try:
        kit = ToolKit(cs, exclude_dangerous=d.get("exclude_dangerous", False))
        fn = {"openai": kit.to_openai_tools, "anthropic": kit.to_anthropic_tools, "gemini": kit.to_gemini_tools}.get(fw, kit.to_openai_tools)
        schema = fn()
        return jsonify({"schema": schema, "tools_count": len(schema), "framework": fw})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/assistant")
def assistant():
    return _r("AI Assistant", """
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<style>
.md-body{line-height:1.7;font-size:0.875rem}
.md-body p{margin:0.5em 0}
.md-body h1,.md-body h2,.md-body h3{font-weight:700;margin:0.8em 0 0.4em}
.md-body h1{font-size:1.25rem}.md-body h2{font-size:1.1rem}.md-body h3{font-size:1rem}
.md-body ul,.md-body ol{margin:0.4em 0;padding-left:1.5em}
.md-body li{margin:0.2em 0}
.md-body code:not(pre code){background:rgba(100,116,139,0.15);padding:0.15em 0.4em;border-radius:4px;font-size:0.82em}
.md-body pre{background:#1e293b;color:#e2e8f0;border-radius:8px;padding:1em;overflow-x:auto;margin:0.6em 0;position:relative}
.md-body pre code{background:none;padding:0;font-size:0.82em}
.md-body blockquote{border-left:3px solid #6366f1;padding-left:0.8em;margin:0.5em 0;color:#64748b}
.md-body table{border-collapse:collapse;width:100%;margin:0.5em 0;font-size:0.82em}
.md-body th,.md-body td{border:1px solid #e2e8f0;padding:0.4em 0.8em;text-align:left}
.dark .md-body th,.dark .md-body td{border-color:#334155}
.md-body th{background:#f1f5f9;font-weight:600}.dark .md-body th{background:#1e293b}
.md-body a{color:#4c6ef5;text-decoration:underline}
.md-body img{max-width:100%;border-radius:8px;margin:0.5em 0}
.md-body hr{border:none;border-top:1px solid #e2e8f0;margin:1em 0}
.dark .md-body hr{border-color:#334155}
.md-body strong{font-weight:700}
.copy-btn{position:absolute;top:8px;right:8px;background:rgba(255,255,255,0.1);border:none;color:#94a3b8;padding:4px 8px;border-radius:4px;cursor:pointer;font-size:11px}
.copy-btn:hover{background:rgba(255,255,255,0.2);color:#fff}
</style>
<h1 class="text-2xl font-bold mb-6">AI Assistant</h1>
<div class="max-w-3xl mx-auto">
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden flex flex-col" style="height:70vh">
<div id="cm" class="flex-1 overflow-y-auto p-4 space-y-4">
<div class="flex gap-3"><div class="w-8 h-8 rounded-full bg-b-100 dark:bg-b-900/30 flex items-center justify-center text-b-600 dark:text-b-400 flex-shrink-0 text-xs font-bold">TC</div>
<div class="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[80%]"><div class="text-sm md-body"><p>Welcome! Ask me about ToolsConnector — connectors, ToolKit setup, schema generation, or anything else.</p></div></div></div></div>
<div class="border-t border-slate-200 dark:border-slate-800 p-4"><div class="flex gap-2">
<input id="ci" type="text" placeholder="Ask about ToolsConnector..." class="flex-1 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-4 py-2.5 text-sm focus:ring-2 focus:ring-b-500 outline-none" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg()}">
<button onclick="sendMsg()" id="sb" class="px-5 py-2.5 rounded-xl bg-b-600 hover:bg-b-700 text-white text-sm font-medium flex-shrink-0">Send</button></div>
<p class="text-xs text-slate-400 mt-2 text-center">Powered by OpenRouter. Responses may not always be accurate.</p></div></div></div>
<script>
marked.setOptions({breaks:true,gfm:true,highlight:function(code,lang){if(lang&&hljs.getLanguage(lang)){try{return hljs.highlight(code,{language:lang}).value}catch(e){}}return hljs.highlightAuto(code).value}});
let busy=false;
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function renderMd(raw,el){
  let html=marked.parse(raw);
  html=html.replace(/<pre><code/g,'<pre><button class="copy-btn" onclick="navigator.clipboard.writeText(this.parentElement.querySelector(\\x27code\\x27).textContent);this.textContent=\\x27Copied!\\x27;setTimeout(()=>this.textContent=\\x27Copy\\x27,1500)">Copy</button><code');
  el.innerHTML=html;
  el.querySelectorAll('pre code').forEach(b=>{try{hljs.highlightElement(b)}catch(e){}});
}
async function sendMsg(){
if(busy)return;const inp=document.getElementById('ci'),msg=inp.value.trim();if(!msg)return;
inp.value='';busy=true;document.getElementById('sb').disabled=true;
const c=document.getElementById('cm');
c.innerHTML+='<div class="flex gap-3 justify-end"><div class="bg-b-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-[80%]"><div class="text-sm md-body"><p>'+esc(msg)+'</p></div></div><div class="w-8 h-8 rounded-full bg-b-600 flex items-center justify-center text-white flex-shrink-0 text-xs font-bold">You</div></div>';
const aid='a'+Date.now();
c.innerHTML+='<div class="flex gap-3"><div class="w-8 h-8 rounded-full bg-b-100 dark:bg-b-900/30 flex items-center justify-center text-b-600 dark:text-b-400 flex-shrink-0 text-xs font-bold">TC</div><div class="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[80%] w-full"><div class="text-sm md-body" id="'+aid+'"><span class="text-slate-400 animate-pulse">Thinking...</span></div></div></div>';
c.scrollTop=c.scrollHeight;
let raw='';
try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});
const rd=r.body.getReader(),dc=new TextDecoder(),el=document.getElementById(aid);let buf='';
while(true){const{done,value}=await rd.read();if(done)break;buf+=dc.decode(value,{stream:true});
const ls=buf.split(String.fromCharCode(10));buf=ls.pop()||'';for(const l of ls){const lt=l.trim();if(lt.startsWith('data: ')){const d=lt.slice(6);if(d==='[DONE]')break;
try{const p=JSON.parse(d),delta=p.choices&&p.choices[0]&&p.choices[0].delta;if(delta&&delta.content){raw+=delta.content;renderMd(raw,el)}}catch(e){}}}c.scrollTop=c.scrollHeight}
if(!raw){el.innerHTML='<p class="text-slate-400">No response received. Try again.</p>'}
}catch(e){const el=document.getElementById(aid);if(el)el.innerHTML='<p class="text-red-500">Error: '+esc(e.message)+'</p>'}
busy=false;document.getElementById('sb').disabled=false}
</script>""")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    d = request.get_json(force=True)
    msg = d.get("message", "")
    if not msg:
        return jsonify({"error": "No message"}), 400
    names = list_connectors()
    specs = _all_specs()
    cl = ", ".join(f"{specs[n]['display_name']} ({n})" for n in names)
    cats = set(specs[n]["category"] for n in names)
    sp = f"""You are the ToolsConnector AI assistant helping developers.

## What is ToolsConnector?
A universal tool-connection primitive for Python. Standardized way to connect AI agents and apps to 50 third-party tools across {len(cats)} categories. A primitive, not a platform.

## Connectors ({len(names)})
{cl}

## Categories: {', '.join(_cat(c) for c in sorted(cats))}

## How ToolKit Works
```python
from toolsconnector.serve import ToolKit
kit = ToolKit(["gmail", "slack"], credentials={{"gmail": "tok", "slack": "tok"}})
tools = kit.to_openai_tools()      # OpenAI
tools = kit.to_anthropic_tools()   # Anthropic
tools = kit.to_gemini_tools()      # Gemini
result = await kit.aexecute("gmail_list_emails", {{"query": "is:unread"}})
kit.serve_mcp()  # MCP server
```

## Install: `pip install toolsconnector` or `pip install toolsconnector[gmail,slack]`

## Key Features
50 connectors, 395 actions, 17 categories. OpenAI/Anthropic/Gemini schemas. MCP server. Circuit breakers, retries, timeouts. Async-first + sync wrappers. JSON Schema validation. Dangerous action filtering. Multi-tenant. BYOK auth.

Be concise, technical, include code examples."""

    if not OPENROUTER_API_KEY:
        def no_key():
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "OPENROUTER_API_KEY not set. Export it to enable the AI assistant."}}]}) + "\n\n"
            yield "data: [DONE]\n\n"
        return Response(no_key(), mimetype="text/event-stream")

    def stream():
        try:
            with httpx.Client(timeout=60.0) as client:
                with client.stream("POST", OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/toolsconnector",
                        "X-OpenRouter-Title": "ToolsConnector",
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": [
                            {"role": "system", "content": sp},
                            {"role": "user", "content": msg},
                        ],
                        "stream": True,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        body = resp.read().decode()
                        yield f"data: {json.dumps({'choices': [{'delta': {'content': f'API error {resp.status_code}: {body[:200]}'}}]})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    for line in resp.iter_lines():
                        if line:
                            yield line + "\n\n"
                yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'choices': [{'delta': {'content': f'Error: {e}'}}]})}\n\n"
            yield "data: [DONE]\n\n"
    return Response(stream(), mimetype="text/event-stream")


@app.route("/health")
def health_page():
    return _r("Health", """
<h1 class="text-2xl font-bold mb-6">Health Dashboard</h1>
<div id="hl" class="text-center py-16"><div class="inline-block w-8 h-8 border-4 border-b-200 border-t-b-600 rounded-full animate-spin"></div><p class="text-sm text-slate-500 mt-3">Checking connector health...</p></div>
<div id="hc" class="hidden">
<div class="grid grid-cols-3 gap-4 mb-8" id="hs"></div>
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
<table class="w-full text-sm"><thead class="bg-slate-50 dark:bg-slate-800/50"><tr>
<th class="text-left px-4 py-3 font-medium text-slate-600 dark:text-slate-400">Connector</th>
<th class="text-left px-4 py-3 font-medium text-slate-600 dark:text-slate-400">Status</th>
<th class="text-left px-4 py-3 font-medium text-slate-600 dark:text-slate-400">Actions</th>
<th class="text-left px-4 py-3 font-medium text-slate-600 dark:text-slate-400">Spec</th>
<th class="text-left px-4 py-3 font-medium text-slate-600 dark:text-slate-400">Details</th></tr></thead>
<tbody id="ht" class="divide-y divide-slate-100 dark:divide-slate-800"></tbody></table></div></div>
<script>
fetch('/api/health').then(r=>r.json()).then(d=>{
document.getElementById('hl').classList.add('hidden');document.getElementById('hc').classList.remove('hidden');
const box=(v,c,l)=>`<div class="p-4 rounded-xl bg-${c}-50 dark:bg-${c}-900/20 border border-${c}-200 dark:border-${c}-800 text-center"><div class="text-2xl font-bold text-${c}-600 dark:text-${c}-400">${v}</div><div class="text-xs text-${c}-700 dark:text-${c}-300 font-medium">${l}</div></div>`;
document.getElementById('hs').innerHTML=box(d.healthy,'emerald','Healthy')+box(d.degraded,'amber','Degraded')+box(d.unavailable,'red','Unavailable');
const t=document.getElementById('ht');
d.reports.forEach(r=>{const ok=r.healthy;
t.innerHTML+=`<tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50"><td class="px-4 py-3 font-medium"><a href="/connector/${r.connector_name}" class="text-b-600 dark:text-b-400 hover:underline">${r.connector_name}</a></td><td class="px-4 py-3"><span class="flex items-center gap-2"><span class="inline-block w-2.5 h-2.5 rounded-full ${ok?'bg-emerald-500':'bg-red-500'}"></span>${ok?'Healthy':'Unhealthy'}</span></td><td class="px-4 py-3">${r.actions_count}</td><td class="px-4 py-3">${r.spec_valid?'<span class="text-xs px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700">Valid</span>':'<span class="text-xs px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-700">Invalid</span>'}</td><td class="px-4 py-3 text-xs text-slate-500">${r.error||'-'}</td></tr>`})
}).catch(e=>{document.getElementById('hl').innerHTML='<p class="text-red-500">Failed: '+e.message+'</p>'});
</script>""")


@app.route("/api/health")
def api_health():
    import asyncio
    checker = HealthChecker()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                report = pool.submit(lambda: asyncio.run(checker.check_all())).result()
        else:
            report = loop.run_until_complete(checker.check_all())
    except RuntimeError:
        report = asyncio.run(checker.check_all())
    return jsonify({
        "total": report.total, "healthy": report.healthy,
        "degraded": report.degraded, "unavailable": report.unavailable,
        "reports": [{"connector_name": r.connector_name, "healthy": r.healthy,
            "error": r.error, "suggestion": r.suggestion, "actions_count": r.actions_count,
            "spec_valid": r.spec_valid, "checked_at": r.checked_at} for r in report.reports],
    })


# -- Docs routes -----------------------------------------------------------
_DOCS_DIR = Path(__file__).parent.parent / "docs"
_EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
_README_PATH = Path(__file__).parent.parent / "README.md"

_DOC_PAGES = [
    ("quickstart", "Quickstart", "guides/quickstart.md", "Get started in 5 minutes"),
    ("mcp-server", "MCP Server", "guides/mcp-server.md", "Claude Desktop and Cursor setup"),
    ("ai-frameworks", "AI Frameworks", "guides/ai-frameworks.md", "OpenAI, Anthropic, Gemini, LangChain"),
    ("credentials", "Credentials", "guides/credentials.md", "BYOK, env vars, KeyStore"),
    ("resilience", "Resilience", "guides/resilience.md", "Circuit breakers, retries, timeouts"),
    ("adding-connector", "Adding a Connector", "guides/adding-connector.md", "Build your own connector"),
    ("api-reference", "API Reference", "API.md", "All classes and methods"),
    ("architecture-faq", "Architecture FAQ", "ARCHITECTURE_FAQ.md", "Design decisions and reasoning"),
]

try:
    import markdown as _md_lib
    _HAS_MD_LIB = True
except ImportError:
    _HAS_MD_LIB = False

def _render_md_file(filepath: Path) -> str:
    """Read a markdown file and convert to HTML."""
    if not filepath.exists():
        return "<p class='text-red-500'>File not found.</p>"
    raw = filepath.read_text(encoding="utf-8")
    if _HAS_MD_LIB:
        html = _md_lib.markdown(raw, extensions=["fenced_code", "tables", "toc", "codehilite"])
    else:
        # Fallback: use marked.js on the client side
        import html as _html
        escaped = _html.escape(raw)
        html = f"""<div id="md-target" class="md-body"></div>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<script>
marked.setOptions({{breaks:true,gfm:true,highlight:function(code,lang){{if(lang&&hljs.getLanguage(lang)){{try{{return hljs.highlight(code,{{language:lang}}).value}}catch(e){{}}}}return hljs.highlightAuto(code).value}}}});
const raw = {json.dumps(raw)};
document.getElementById('md-target').innerHTML = marked.parse(raw);
document.querySelectorAll('pre code').forEach(b=>{{try{{hljs.highlightElement(b)}}catch(e){{}}}});
</script>"""
    return html

@app.route("/docs")
def docs_index():
    cards = ""
    for slug, title, _, desc in _DOC_PAGES:
        cards += f'''<a href="/docs/{slug}" class="group block p-5 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-b-400 hover:shadow-lg transition-all bg-white dark:bg-slate-900">
<div class="font-semibold text-b-700 dark:text-b-400 group-hover:text-b-600">{title}</div>
<p class="text-sm text-slate-500 mt-1">{desc}</p></a>'''

    examples = ""
    if _EXAMPLES_DIR.exists():
        for f in sorted(_EXAMPLES_DIR.glob("*.py")):
            name = f.stem.replace("_", " ").title()
            examples += f'<a href="/docs/example/{f.stem}" class="block px-4 py-2.5 rounded-lg text-sm hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300">{name}</a>'

    return _r("Documentation", f"""
<h1 class="text-2xl font-bold mb-2">Documentation</h1>
<p class="text-slate-500 mb-8">Guides, API reference, and examples for ToolsConnector.</p>
<h2 class="text-lg font-semibold mb-4">Guides</h2>
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-10">{cards}</div>
<h2 class="text-lg font-semibold mb-4">Examples</h2>
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1">{examples or '<p class="text-slate-400 p-4">No examples found.</p>'}</div>
""")

@app.route("/docs/<slug>")
def docs_page(slug: str):
    # Find the matching doc page
    filepath = None
    title = slug
    for s, t, path, _ in _DOC_PAGES:
        if s == slug:
            filepath = _DOCS_DIR / path
            title = t
            break
    if filepath is None:
        return _r("Not Found", "<p class='text-red-500'>Documentation page not found.</p>"), 404

    # Sidebar nav
    sidebar = ""
    for s, t, _, _ in _DOC_PAGES:
        active = "bg-b-100 dark:bg-b-900/30 text-b-700 dark:text-b-400 font-medium" if s == slug else "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
        sidebar += f'<a href="/docs/{s}" class="block px-3 py-2 rounded-lg text-sm {active}">{t}</a>'

    content = _render_md_file(filepath)

    return _r(title, f"""
<div class="flex gap-8">
<nav class="hidden lg:block w-56 flex-shrink-0">
<div class="sticky top-24 space-y-1">
<a href="/docs" class="block px-3 py-2 rounded-lg text-sm text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 mb-2 font-medium">&larr; All Docs</a>
{sidebar}
</div></nav>
<div class="flex-1 min-w-0">
<article class="md-body prose-slate max-w-none">
<style>
.md-body h1{{font-size:1.5rem;font-weight:700;margin:1em 0 0.5em;border-bottom:1px solid #e2e8f0;padding-bottom:0.3em}}
.md-body h2{{font-size:1.25rem;font-weight:600;margin:1.2em 0 0.4em}}
.md-body h3{{font-size:1.1rem;font-weight:600;margin:1em 0 0.3em}}
.md-body p{{margin:0.5em 0;line-height:1.7}}
.md-body ul,.md-body ol{{padding-left:1.5em;margin:0.5em 0}}
.md-body li{{margin:0.3em 0}}
.md-body code:not(pre code){{background:rgba(100,116,139,0.12);padding:0.15em 0.4em;border-radius:4px;font-size:0.85em}}
.md-body pre{{background:#1e293b;color:#e2e8f0;border-radius:8px;padding:1em;overflow-x:auto;margin:0.8em 0}}
.md-body pre code{{background:none;padding:0;font-size:0.85em}}
.md-body blockquote{{border-left:3px solid #6366f1;padding-left:0.8em;margin:0.5em 0;color:#64748b}}
.md-body table{{border-collapse:collapse;width:100%;margin:0.8em 0;font-size:0.85em}}
.md-body th,.md-body td{{border:1px solid #e2e8f0;padding:0.5em 0.8em;text-align:left}}
.dark .md-body th,.dark .md-body td{{border-color:#334155}}
.md-body th{{background:#f1f5f9;font-weight:600}}.dark .md-body th{{background:#1e293b}}
.md-body a{{color:#4c6ef5;text-decoration:underline}}
.md-body hr{{border:none;border-top:1px solid #e2e8f0;margin:1.5em 0}}
.dark .md-body hr{{border-color:#334155}}
.md-body img{{max-width:100%;border-radius:8px}}
</style>
{content}
</article></div></div>""")

@app.route("/docs/example/<name>")
def docs_example(name: str):
    filepath = _EXAMPLES_DIR / f"{name}.py"
    if not filepath.exists():
        return _r("Not Found", "<p class='text-red-500'>Example not found.</p>"), 404

    code = filepath.read_text(encoding="utf-8")
    import html as _html
    escaped = _html.escape(code)
    title = name.replace("_", " ").title()

    return _r(title, f"""
<div class="mb-4"><a href="/docs" class="text-sm text-b-600 dark:text-b-400 hover:underline">&larr; Back to Docs</a></div>
<h1 class="text-2xl font-bold mb-2">{title}</h1>
<p class="text-slate-500 mb-6">examples/{name}.py</p>
<div class="rounded-xl overflow-hidden border border-slate-200 dark:border-slate-800 relative">
<button onclick="navigator.clipboard.writeText(document.getElementById('excode').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)" class="absolute top-3 right-3 bg-slate-700 text-slate-300 text-xs px-3 py-1 rounded hover:bg-slate-600 z-10">Copy</button>
<pre class="bg-slate-900 text-slate-100 p-5 overflow-x-auto text-sm leading-relaxed"><code id="excode" class="language-python">{escaped}</code></pre>
</div>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<script>hljs.highlightElement(document.getElementById('excode'));</script>
""")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    print(f"\n  ToolsConnector Playground")
    print(f"  http://127.0.0.1:{port}\n")
    app.run(debug=debug, host="0.0.0.0", port=port)
