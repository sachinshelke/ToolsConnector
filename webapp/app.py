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
    n_connectors = s["connectors"]
    n_actions = s["actions"]
    n_categories = s["categories"]
    remaining_connectors = max(0, n_connectors - 20)

    # Category icons (SVG paths) keyed by category slug
    _CAT_ICONS = {
        "communication": '<path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"/>',
        "crm": '<path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/>',
        "project_management": '<path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z"/>',
        "code_platform": '<path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5"/>',
        "devops": '<path stroke-linecap="round" stroke-linejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7"/>',
        "database": '<path stroke-linecap="round" stroke-linejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75"/>',
        "productivity": '<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"/>',
        "ai_ml": '<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z"/>',
        "finance": '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z"/>',
        "marketing": '<path stroke-linecap="round" stroke-linejoin="round" d="M10.34 15.84c-.688-.06-1.386-.09-2.09-.09H7.5a4.5 4.5 0 110-9h.75c.704 0 1.402-.03 2.09-.09m0 9.18c.253.962.584 1.892.985 2.783.247.55.06 1.21-.463 1.511l-.657.38c-.551.318-1.26.117-1.527-.461a20.845 20.845 0 01-1.44-4.282m3.102.069a18.03 18.03 0 01-.59-4.59c0-1.586.205-3.124.59-4.59m0 9.18a23.848 23.848 0 018.835 2.535M10.34 6.66a23.847 23.847 0 008.835-2.535m0 0A23.74 23.74 0 0018.795 3m.38 1.125a23.91 23.91 0 011.014 5.395m-1.014 8.855c-.118.38-.245.754-.38 1.125m.38-1.125a23.91 23.91 0 001.014-5.395m0-3.46c.495.413.811 1.035.811 1.73 0 .695-.316 1.317-.811 1.73m0-3.46a24.347 24.347 0 010 3.46"/>',
        "storage": '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z"/>',
        "message_queue": '<path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"/>',
        "analytics": '<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/>',
        "security": '<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"/>',
        "knowledge": '<path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"/>',
        "ecommerce": '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 00-16.536-1.84M7.5 14.25L5.106 5.272M6 20.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm12.75 0a.75.75 0 11-1.5 0 .75.75 0 011.5 0z"/>',
        "custom": '<path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17l-5.648 3.165a.75.75 0 01-1.022-.868l1.023-5.958-4.326-4.234a.75.75 0 01.418-1.276l5.974-.87L10.59 0a.75.75 0 011.32 0l2.748 5.13 5.974.87a.75.75 0 01.418 1.276l-4.326 4.234 1.023 5.958a.75.75 0 01-1.022.868l-5.648-3.165z"/>',
    }
    _CAT_COLORS = {
        "communication": "#3B82F6", "crm": "#F59E0B", "project_management": "#8B5CF6",
        "code_platform": "#1E293B", "devops": "#06B6D4", "database": "#10B981",
        "productivity": "#F97316", "ai_ml": "#7C3AED", "finance": "#6366F1",
        "marketing": "#EC4899", "storage": "#14B8A6", "message_queue": "#EF4444",
        "analytics": "#8B5CF6", "security": "#059669", "knowledge": "#0EA5E9",
        "ecommerce": "#84CC16", "custom": "#6366F1",
    }

    # Category grid for section 8
    cats_html = ""
    for c, n in s["by_category"].items():
        icon_path = _CAT_ICONS.get(c, _CAT_ICONS["custom"])
        icon_color = _CAT_COLORS.get(c, "#6366F1")
        cats_html += (
            f'<a href="/connectors?cat={c}" class="group flex items-center gap-4 p-4 rounded-xl border border-slate-200'
            f' dark:border-slate-800 hover:border-b-400 hover:shadow-lg transition-all'
            f' bg-white dark:bg-slate-900">'
            f'<div class="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style="background:{icon_color}15">'
            f'<svg class="w-5 h-5" fill="none" stroke="{icon_color}" stroke-width="1.5" viewBox="0 0 24 24">{icon_path}</svg></div>'
            f'<div><div class="text-sm font-semibold text-slate-700 dark:text-slate-300">{_cat(c)}</div>'
            f'<div class="text-xs text-slate-400">{n} connectors</div></div></a>'
        )

    # Tool logos for the logo cloud
    tool_logos = [
        ("gmail", "Gmail"), ("slack", "Slack"), ("github", "GitHub"),
        ("stripe", "Stripe"), ("openai", "OpenAI"), ("anthropic", "Anthropic"),
        ("notion", "Notion"), ("jira", "Jira"), ("discord", "Discord"),
        ("amazons3", "AWS S3"), ("salesforce", "Salesforce"), ("hubspot", "HubSpot"),
        ("twilio", "Twilio"), ("shopify", "Shopify"), ("dropbox", "Dropbox"),
        ("figma", "Figma"), ("linear", "Linear"), ("asana", "Asana"),
        ("googlecalendar", "Calendar"), ("microsoftteams", "Teams"),
    ]
    logos_html = "".join(
        f'<div class="flex flex-col items-center gap-2 p-4">'
        f'<img src="https://cdn.simpleicons.org/{si}" alt="{label}" class="w-10 h-10 dark:invert dark:brightness-200 dark:contrast-75"'
        f' onerror="this.parentElement.style.display=\'none\'">'
        f'<span class="text-xs text-slate-500 dark:text-slate-400 font-medium">{label}</span></div>'
        for si, label in tool_logos
    )

    return _r("Home", f"""
<!-- Section 1: Hero -->
<section class="text-center pt-12 pb-16 sm:pt-20 sm:pb-24">
  <h1 class="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight mb-6">
    <span class="bg-gradient-to-r from-b-600 via-purple-600 to-b-600 bg-clip-text text-transparent">One library, every tool.</span>
  </h1>
  <p class="text-lg sm:text-xl text-slate-600 dark:text-slate-400 max-w-3xl mx-auto leading-relaxed mb-10">
    Connect AI agents and Python apps to {n_connectors}+ APIs through a single, standardized interface.
    Open source. Self-hosted. Works everywhere.
  </p>
  <div class="flex flex-wrap justify-center gap-8 sm:gap-12 mb-10">
    <div class="text-center">
      <div class="text-3xl sm:text-4xl font-bold text-b-600 dark:text-b-400">{n_connectors}</div>
      <div class="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">Connectors</div>
    </div>
    <div class="text-center">
      <div class="text-3xl sm:text-4xl font-bold text-purple-600 dark:text-purple-400">{n_actions:,}</div>
      <div class="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">Actions</div>
    </div>
    <div class="text-center">
      <div class="text-3xl sm:text-4xl font-bold text-emerald-600 dark:text-emerald-400">{n_categories}</div>
      <div class="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">Categories</div>
    </div>
  </div>
  <div class="flex flex-col sm:flex-row justify-center gap-3">
    <a href="/docs/quickstart" class="inline-flex items-center justify-center gap-2 px-7 py-3 rounded-xl bg-b-700 hover:bg-b-800 text-white font-semibold transition-colors shadow-lg shadow-b-700/25">
      Get Started
      <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"/></svg>
    </a>
    <a href="/connectors" class="inline-flex items-center justify-center gap-2 px-7 py-3 rounded-xl border border-slate-300 dark:border-slate-700 hover:border-b-400 dark:hover:border-b-400 font-semibold transition-colors bg-white dark:bg-slate-900">
      Browse Connectors
    </a>
  </div>
</section>

<!-- Section 2: The Problem -->
<section class="py-16 sm:py-20">
  <div class="text-center mb-12">
    <h2 class="text-2xl sm:text-3xl font-bold mb-3">Why this exists</h2>
    <p class="text-slate-500 dark:text-slate-400">Three problems every developer building with APIs hits.</p>
  </div>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="w-12 h-12 rounded-xl bg-red-50 dark:bg-red-900/20 flex items-center justify-center mb-4">
        <svg class="w-6 h-6 text-red-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25a2.25 2.25 0 01-2.25-2.25v-2.25z"/>
        </svg>
      </div>
      <h3 class="text-lg font-semibold mb-2">Fragmented SDKs</h3>
      <p class="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">Every tool has a different SDK, auth pattern, and error format. Managing 10 SDKs in one project is painful.</p>
    </div>
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="w-12 h-12 rounded-xl bg-amber-50 dark:bg-amber-900/20 flex items-center justify-center mb-4">
        <svg class="w-6 h-6 text-amber-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z"/>
        </svg>
      </div>
      <h3 class="text-lg font-semibold mb-2">AI agents need tools</h3>
      <p class="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">LLMs can't call APIs directly. You need schemas, execution, retries, and rate limiting for every tool.</p>
    </div>
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="w-12 h-12 rounded-xl bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center mb-4">
        <svg class="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"/>
        </svg>
      </div>
      <h3 class="text-lg font-semibold mb-2">Build vs. Buy</h3>
      <p class="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">Hosted platforms lock you in. Raw APIs take weeks. There's no open-source middle ground.</p>
    </div>
  </div>
  <div class="text-center mt-10">
    <svg class="w-6 h-6 mx-auto text-slate-300 dark:text-slate-600 mb-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5L12 21m0 0l-7.5-7.5M12 21V3"/></svg>
    <p class="text-sm font-semibold text-b-600 dark:text-b-400">ToolsConnector solves all three.</p>
  </div>
</section>

<!-- Section 3: How It Works -->
<section class="py-16 sm:py-20">
  <div class="text-center mb-12">
    <h2 class="text-2xl sm:text-3xl font-bold mb-3">How it works</h2>
    <p class="text-slate-500 dark:text-slate-400">Three steps. From install to production.</p>
  </div>
  <div class="grid grid-cols-1 xl:grid-cols-3 gap-5 items-stretch">
    <!-- Step 1 -->
    <div class="flex flex-col rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
      <div class="flex items-center gap-3 px-4 pt-4 pb-2">
        <div class="w-8 h-8 rounded-full bg-b-600 text-white flex items-center justify-center text-sm font-bold flex-shrink-0">1</div>
        <div>
          <h3 class="text-lg font-semibold">Install</h3>
          <p class="text-xs text-slate-400">Pick the connectors you need</p>
        </div>
      </div>
      <div class="flex-1 px-4 pb-4">
        <pre class="bg-slate-900 text-slate-100 rounded-xl p-4 text-xs overflow-hidden h-full flex items-start leading-relaxed"><code><span class="text-emerald-400">$</span> pip install "toolsconnector[gmail]"

<span class="text-slate-500"># Or multiple connectors</span>
<span class="text-emerald-400">$</span> pip install "toolsconnector[gmail,slack]"

<span class="text-slate-500"># Or install everything</span>
<span class="text-emerald-400">$</span> pip install "toolsconnector[all]"</code></pre>
      </div>
    </div>
    <!-- Step 2 -->
    <div class="flex flex-col rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
      <div class="flex items-center gap-3 px-4 pt-4 pb-2">
        <div class="w-8 h-8 rounded-full bg-b-600 text-white flex items-center justify-center text-sm font-bold flex-shrink-0">2</div>
        <div>
          <h3 class="text-lg font-semibold">Connect</h3>
          <p class="text-xs text-slate-400">One object, any number of tools</p>
        </div>
      </div>
      <div class="flex-1 px-4 pb-4">
        <pre class="bg-slate-900 text-slate-100 rounded-xl p-4 text-xs overflow-hidden h-full flex items-start leading-relaxed"><code><span class="text-purple-400">from</span> <span class="text-emerald-400">toolsconnector.serve</span> <span class="text-purple-400">import</span> ToolKit

kit = ToolKit(
  [<span class="text-amber-300">"gmail"</span>, <span class="text-amber-300">"slack"</span>],
  credentials={{
    <span class="text-amber-300">"gmail"</span>: os.environ[<span class="text-amber-300">"GMAIL_TOKEN"</span>],
  }}
)</code></pre>
      </div>
    </div>
    <!-- Step 3 -->
    <div class="flex flex-col rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
      <div class="flex items-center gap-3 px-4 pt-4 pb-2">
        <div class="w-8 h-8 rounded-full bg-b-600 text-white flex items-center justify-center text-sm font-bold flex-shrink-0">3</div>
        <div>
          <h3 class="text-lg font-semibold">Use anywhere</h3>
          <p class="text-xs text-slate-400">Python, MCP, or any AI framework</p>
        </div>
      </div>
      <div class="flex-1 px-4 pb-4">
        <pre class="bg-slate-900 text-slate-100 rounded-xl p-4 text-xs overflow-hidden h-full flex items-start leading-relaxed"><code><span class="text-slate-500"># Execute directly</span>
kit.execute(<span class="text-amber-300">"gmail_list_emails"</span>, {{}})

<span class="text-slate-500"># MCP Server (Claude Desktop)</span>
kit.serve_mcp()

<span class="text-slate-500"># OpenAI / Anthropic schemas</span>
tools = kit.to_openai_tools()</code></pre>
      </div>
    </div>
  </div>
  <!-- Output formats row -->
  <div class="mt-8 flex flex-wrap items-center justify-center gap-3 text-xs">
    <span class="text-slate-400 font-medium">Output formats:</span>
    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium text-slate-600 dark:text-slate-300">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5"/></svg>
      Python SDK</span>
    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium text-slate-600 dark:text-slate-300">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7"/></svg>
      MCP Server</span>
    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium text-slate-600 dark:text-slate-300">
      <img src="https://cdn.simpleicons.org/openai" alt="" class="w-3.5 h-3.5 dark:invert" onerror="this.style.display='none'">
      OpenAI Tools</span>
    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium text-slate-600 dark:text-slate-300">
      <img src="https://cdn.simpleicons.org/anthropic" alt="" class="w-3.5 h-3.5 dark:invert" onerror="this.style.display='none'">
      Anthropic Tools</span>
    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium text-slate-600 dark:text-slate-300">
      <img src="https://cdn.simpleicons.org/google" alt="" class="w-3.5 h-3.5" onerror="this.style.display='none'">
      Gemini Tools</span>
    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium text-slate-600 dark:text-slate-300">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"/></svg>
      LangChain</span>
    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium text-slate-600 dark:text-slate-300">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
      REST API</span>
  </div>
  <div class="text-center mt-4 text-xs text-slate-400">TypeScript, Go, and Java SDKs coming soon.</div>
</section>

<!-- Section 4: Tool Logos -->
<section class="py-16 sm:py-20 border-t border-slate-200 dark:border-slate-800">
  <div class="text-center mb-10">
    <h2 class="text-2xl sm:text-3xl font-bold mb-3">Supported tools</h2>
    <p class="text-slate-500 dark:text-slate-400">{n_connectors} connectors and growing. All standardized.</p>
  </div>
  <div class="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-10 gap-2 max-w-5xl mx-auto mb-8">
    {logos_html}
  </div>
  <div class="text-center">
    <a href="/connectors" class="text-sm font-semibold text-b-600 dark:text-b-400 hover:underline">+{remaining_connectors} more connectors &rarr;</a>
  </div>
</section>

<!-- Section 5: Framework Compatibility -->
<section class="py-16 sm:py-20 border-t border-slate-200 dark:border-slate-800">
  <div class="text-center mb-12">
    <h2 class="text-2xl sm:text-3xl font-bold mb-3">Works with every framework</h2>
    <p class="text-slate-500 dark:text-slate-400">One interface. Every AI platform.</p>
  </div>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 max-w-5xl mx-auto">
    <div class="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="flex items-center gap-3 mb-3">
        <img src="https://cdn.simpleicons.org/openai" alt="OpenAI" class="w-6 h-6 dark:invert" onerror="this.style.display='none'">
        <h3 class="font-semibold">OpenAI</h3>
      </div>
      <code class="text-xs text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded">kit.to_openai_tools()</code>
      <p class="text-xs text-slate-500 mt-2">Function calling</p>
    </div>
    <div class="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="flex items-center gap-3 mb-3">
        <img src="https://cdn.simpleicons.org/anthropic" alt="Anthropic" class="w-6 h-6 dark:invert" onerror="this.style.display='none'">
        <h3 class="font-semibold">Anthropic</h3>
      </div>
      <code class="text-xs text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded">kit.to_anthropic_tools()</code>
      <p class="text-xs text-slate-500 mt-2">Tool use with Claude</p>
    </div>
    <div class="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="flex items-center gap-3 mb-3">
        <svg class="w-6 h-6 text-b-600 dark:text-b-400" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7"/></svg>
        <h3 class="font-semibold">MCP</h3>
      </div>
      <code class="text-xs text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded">kit.serve_mcp()</code>
      <p class="text-xs text-slate-500 mt-2">Claude Desktop, Cursor</p>
    </div>
    <div class="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="flex items-center gap-3 mb-3">
        <svg class="w-6 h-6 text-emerald-600 dark:text-emerald-400" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"/></svg>
        <h3 class="font-semibold">LangChain</h3>
      </div>
      <code class="text-xs text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded">kit.to_langchain_tools()</code>
      <p class="text-xs text-slate-500 mt-2">Agent frameworks</p>
    </div>
  </div>
</section>

<!-- Section 6: Built for Production -->
<section class="py-16 sm:py-20 border-t border-slate-200 dark:border-slate-800">
  <div class="text-center mb-12">
    <h2 class="text-2xl sm:text-3xl font-bold mb-3">Built for production</h2>
    <p class="text-slate-500 dark:text-slate-400">Not a toy. Battle-tested reliability patterns.</p>
  </div>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="w-12 h-12 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 flex items-center justify-center mb-4">
        <svg class="w-6 h-6 text-emerald-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"/>
        </svg>
      </div>
      <h3 class="text-lg font-semibold mb-2">Circuit Breaker</h3>
      <p class="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">Automatic failure isolation. One connector down doesn't take everything with it.</p>
    </div>
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="w-12 h-12 rounded-xl bg-purple-50 dark:bg-purple-900/20 flex items-center justify-center mb-4">
        <svg class="w-6 h-6 text-purple-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182M21.015 4.356v4.992"/>
        </svg>
      </div>
      <h3 class="text-lg font-semibold mb-2">Smart Retries</h3>
      <p class="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">Exponential backoff with jitter. Respects rate limits and retry-after headers.</p>
    </div>
    <div class="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div class="w-12 h-12 rounded-xl bg-b-50 dark:bg-b-900/20 flex items-center justify-center mb-4">
        <svg class="w-6 h-6 text-b-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M10.125 2.25h-4.5c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125v-9M10.125 2.25h.375a9 9 0 019 9v.375M10.125 2.25A3.375 3.375 0 0113.5 5.625v1.5c0 .621.504 1.125 1.125 1.125h1.5a3.375 3.375 0 013.375 3.375M9 15l2.25 2.25L15 12"/>
        </svg>
      </div>
      <h3 class="text-lg font-semibold mb-2">Pre-validation</h3>
      <p class="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">Arguments checked against JSON Schema before hitting the API. Catches mistakes early.</p>
    </div>
  </div>
</section>

<!-- Section 7: Open Source -->
<section class="py-16 sm:py-20 border-t border-slate-200 dark:border-slate-800">
  <div class="text-center max-w-2xl mx-auto">
    <h2 class="text-2xl sm:text-3xl font-bold mb-4">Open source</h2>
    <p class="text-slate-600 dark:text-slate-400 mb-8">Apache 2.0 licensed. Self-hosted. No vendor lock-in.</p>
    <div class="flex flex-col sm:flex-row justify-center gap-3 mb-8">
      <a href="https://github.com/sachinshelke/ToolsConnector" target="_blank" rel="noopener"
         class="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl border border-slate-300 dark:border-slate-700 hover:border-slate-400 dark:hover:border-slate-600 font-semibold transition-colors bg-white dark:bg-slate-900">
        <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
        Star on GitHub
      </a>
    </div>
    <pre class="bg-slate-900 text-slate-100 rounded-xl p-5 text-sm inline-block"><code><span class="text-emerald-400">$</span> pip install toolsconnector</code></pre>
  </div>
</section>

<!-- Section 8: Categories -->
<section class="py-16 sm:py-20 border-t border-slate-200 dark:border-slate-800">
  <div class="text-center mb-8">
    <h2 class="text-2xl sm:text-3xl font-bold mb-3">Browse by category</h2>
  </div>
  <div class="max-w-xl mx-auto mb-8">
    <div class="relative">
      <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg>
      <input type="text" placeholder="Search connectors... (e.g. gmail, slack, stripe)"
        class="w-full pl-10 pr-4 py-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-b-500 focus:border-b-500 outline-none"
        onkeyup="if(event.key==='Enter')location.href='/connectors?q='+this.value">
    </div>
  </div>
  <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 mb-8">
    {cats_html}
  </div>
</section>

<!-- Section 9: Quick Links -->
<section class="py-12 border-t border-slate-200 dark:border-slate-800">
  <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
    <a href="/connectors" class="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-b-400 bg-white dark:bg-slate-900 transition-all hover:shadow-md">
      <div class="w-9 h-9 rounded-lg bg-b-100 dark:bg-b-900/30 flex items-center justify-center text-b-600 dark:text-b-400">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6z"/></svg>
      </div>
      <div class="font-medium text-sm">Browse All</div>
    </a>
    <a href="/playground" class="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-purple-400 bg-white dark:bg-slate-900 transition-all hover:shadow-md">
      <div class="w-9 h-9 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center text-purple-600 dark:text-purple-400">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5"/></svg>
      </div>
      <div class="font-medium text-sm">Playground</div>
    </a>
    <a href="/assistant" class="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-emerald-400 bg-white dark:bg-slate-900 transition-all hover:shadow-md">
      <div class="w-9 h-9 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"/></svg>
      </div>
      <div class="font-medium text-sm">AI Assistant</div>
    </a>
    <a href="/docs" class="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-amber-400 bg-white dark:bg-slate-900 transition-all hover:shadow-md">
      <div class="w-9 h-9 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center text-amber-600 dark:text-amber-400">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.331 0 4.233 1.236 5.426 2.18.76.603 1.574.82 1.574.82s.814-.217 1.574-.82C15.767 19.236 17.669 18 20 18a8.987 8.987 0 013-.512V4.262A8.967 8.967 0 0020 3.75a8.967 8.967 0 00-6 2.292z"/></svg>
      </div>
      <div class="font-medium text-sm">Docs</div>
    </a>
    <a href="/health" class="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-rose-400 bg-white dark:bg-slate-900 transition-all hover:shadow-md">
      <div class="w-9 h-9 rounded-lg bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center text-rose-600 dark:text-rose-400">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"/></svg>
      </div>
      <div class="font-medium text-sm">Health</div>
    </a>
  </div>
</section>""")


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
            m = get_tool_meta(name)
            if m.get("logo"):
                icon = f'<img src="{m["logo"]}" alt="" class="w-8 h-8 rounded-lg flex-shrink-0" onerror="this.style.display=\'none\'">'
            else:
                ini = sp["display_name"][:2].upper()
                icon = f'<div class="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold flex-shrink-0" style="background:{m["color"]}">{ini}</div>'
            html += f'<a href="/connector/{name}" class="group flex items-start gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-b-400 bg-white dark:bg-slate-900 hover:shadow-md transition-all">{icon}<div class="flex-1 min-w-0"><div class="flex items-start justify-between"><div><div class="font-semibold text-b-700 dark:text-b-400">{sp["display_name"]}</div><div class="text-xs text-slate-500 mt-0.5">{name}</div></div><span class="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-medium">{na}</span></div><p class="text-sm text-slate-600 dark:text-slate-400 mt-1.5 line-clamp-2">{sp.get("description","")}</p></div></a>'
        html += "</div>"
    return _r("Connectors", f"""
<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
<h1 class="text-2xl font-bold">Connectors</h1>
<div class="relative w-full sm:w-72"><svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg>
<input type="text" value="{q}" placeholder="Filter connectors..." class="w-full pl-9 pr-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-b-500 outline-none" onkeyup="if(event.key==='Enter')location.href='/connectors?q='+this.value+'&cat={cf}'"></div></div>
{html or '<p class="text-slate-500 py-8 text-center">No connectors match your search.</p>'}""")


def _action_scope(aname: str, act: dict) -> str:
    """Determine the scope label for an action."""
    if act.get("requires_scope"):
        return act["requires_scope"]
    if act.get("dangerous"):
        return "destructive"
    if any(aname.startswith(p) for p in ("list_", "get_", "search_", "query_", "describe_", "find_", "fetch_")):
        return "read"
    if any(aname.startswith(p) for p in ("create_", "send_", "add_", "insert_", "import_", "append_", "upload_", "batch_create", "upsert_")):
        return "write"
    if any(aname.startswith(p) for p in ("update_", "modify_", "rename_", "move_", "assign_", "mark_", "star_", "unstar_", "batch_modify", "batch_update", "merge_", "transition_", "complete_", "subscribe_", "unsubscribe_")):
        return "modify"
    if any(aname.startswith(p) for p in ("delete_", "trash_", "untrash_", "remove_", "cancel_", "void_", "purge_", "clear_", "empty_", "batch_delete", "ban_", "block_", "deactivate_", "revoke_")):
        return "delete"
    return "action"


def _best_first_action(actions: dict) -> str:
    """Pick the most useful action for quickstart examples."""
    # Prefer specific common actions first
    preferred = [
        "list_emails", "list_messages", "list_files", "list_events",
        "list_repos", "list_channels", "list_contacts", "list_issues",
        "list_records", "list_tasks", "list_products", "list_projects",
        "get_values", "get_spreadsheet", "get_document",
        "search", "query",
    ]
    for name in preferred:
        if name in actions:
            return name
    # Fall back to first list_ or get_ action
    for aname in sorted(actions.keys()):
        if aname.startswith("list_") or aname.startswith("get_"):
            return aname
    return sorted(actions.keys())[0] if actions else "action"


def _example_value(p: dict) -> str:
    """Generate a realistic example value for a parameter."""
    ptype = p.get("type", "string")
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
    # string or fallback
    name = p.get("name", "value")
    return f'"your-{name}"'


def _action_section_html(aname: str, act: dict, connector_name: str) -> str:
    """Render one action as a full visible section (no click-to-expand)."""
    import html as _html
    params = act.get("parameters", [])
    scope = _action_scope(aname, act)
    is_dangerous = act.get("dangerous", False)
    desc = act.get("description", "")
    returns = act.get("returns", {})
    return_type = returns.get("type", "dict") if isinstance(returns, dict) else str(returns) if returns else "dict"

    # Scope badge
    scope_bg = {
        "read": "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400",
        "write": "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
        "modify": "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
        "delete": "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400",
        "destructive": "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400",
    }
    badge_cls = scope_bg.get(scope, "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400")
    scope_badge = f'<span class="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full {badge_cls}">{scope}</span>'
    warn_html = ' <span class="text-amber-500 text-sm" title="Destructive action">&#9888;</span>' if is_dangerous else ""

    # Parameters block
    params_html = ""
    if params:
        rows = ""
        for p in params:
            ptype = p.get("type", "any")
            req_label = '<span class="text-red-400 font-medium">required</span>' if p.get("required") else '<span class="text-slate-300 dark:text-slate-500">optional</span>'
            pdesc = _html.escape(p.get("description", "")) if p.get("description") else '<span class="text-slate-300">&mdash;</span>'
            rows += f'''<div class="flex items-start gap-3 text-xs">
<code class="font-semibold text-slate-700 dark:text-slate-300 w-28 flex-shrink-0">{p["name"]}</code>
<span class="text-purple-500 dark:text-purple-400 w-16 flex-shrink-0">{ptype}</span>
<span class="w-14 flex-shrink-0">{req_label}</span>
<span class="text-slate-500 dark:text-slate-400">{pdesc}</span>
</div>'''
        params_html = f'''<div class="mb-3">
<div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">Parameters</div>
<div class="bg-slate-50 dark:bg-slate-800/30 rounded-lg p-3 space-y-1.5">{rows}</div>
</div>'''

    # Returns block
    returns_html = f'''<div class="mb-3 text-xs">
<span class="text-slate-400">Returns:</span>
<code class="font-mono text-b-600 dark:text-b-400 ml-1">{_html.escape(str(return_type))}</code>
</div>'''

    # Example code with real values
    required_params = [p for p in params if p.get("required")]
    optional_params = [p for p in params if not p.get("required")]
    example_params = required_params + optional_params[:2]
    if example_params:
        args_str = ", ".join(f'"{p["name"]}": {_example_value(p)}' for p in example_params)
        example_code = f'result = kit.execute("{connector_name}_{aname}", {{{args_str}}})'
    else:
        example_code = f'result = kit.execute("{connector_name}_{aname}", {{}})'
    escaped_code = _html.escape(example_code)

    return f'''<section id="action-{aname}" class="scroll-mt-20 py-6 border-b border-slate-100 dark:border-slate-800/50 px-5">
<div class="flex items-center gap-2 mb-1.5">
<h3 class="text-sm font-bold font-mono text-slate-800 dark:text-slate-200">{aname}</h3>
{scope_badge}{warn_html}
</div>
<p class="text-sm text-slate-500 dark:text-slate-400 mb-4">{_html.escape(desc)}</p>
{params_html}
{returns_html}
<div class="relative">
<pre class="text-[11px] bg-slate-900 text-slate-100 rounded-lg p-3 overflow-x-auto"><code class="language-python">{escaped_code}</code></pre>
<button onclick="navigator.clipboard.writeText(this.previousElementSibling.querySelector('code').textContent.trim());this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)" class="absolute top-2 right-2 text-[10px] px-2 py-0.5 rounded bg-slate-700 text-slate-400 hover:text-white cursor-pointer">Copy</button>
</div>
</section>'''


def _sidebar_html(actions: dict, name: str) -> str:
    """Render a sticky left sidebar with section links and action links.

    Desktop: visible as a sidebar.  Mobile: hidden by default, toggled via a
    floating dropdown button.
    """
    action_count = len(actions)
    action_links = ""
    for aname in sorted(actions.keys()):
        action_links += f'<a href="#action-{aname}" class="sidebar-link action-link block px-3 py-1 text-xs font-mono text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 rounded truncate" data-section="action-{aname}" title="{aname}">{aname}</a>\n'

    sidebar_inner = f'''<a href="/connectors" class="block px-3 py-1.5 rounded text-sm text-slate-400 hover:text-slate-600 mb-2">&larr; All Connectors</a>
<a href="#overview" class="sidebar-link block px-3 py-1.5 rounded text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 font-medium" data-section="overview">Overview</a>
<a href="#install" class="sidebar-link block px-3 py-1.5 rounded text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 font-medium" data-section="install">Install</a>
<a href="#quickstart" class="sidebar-link block px-3 py-1.5 rounded text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 font-medium" data-section="quickstart">Quick Start</a>
<a href="#actions" class="sidebar-link block px-3 py-1.5 rounded text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 font-medium" data-section="actions">Actions</a>
<div class="mt-3 pt-3 border-t border-slate-200 dark:border-slate-800">
<span class="px-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Actions ({action_count})</span>
<div class="mt-1 space-y-0">
{action_links}</div>
</div>
<div class="mt-3 pt-3 border-t border-slate-200 dark:border-slate-800">
<a href="#auth" class="sidebar-link block px-3 py-1.5 rounded text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 font-medium" data-section="auth">Authentication</a>
</div>'''

    return f'''<!-- Mobile sidebar toggle -->
<div class="lg:hidden fixed bottom-4 right-4 z-40">
<button onclick="document.getElementById('mobile-sidebar').classList.toggle('hidden')" class="w-12 h-12 rounded-full bg-b-600 text-white shadow-lg flex items-center justify-center hover:bg-b-700 transition-colors">
<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/></svg>
</button>
</div>
<div id="mobile-sidebar" class="hidden lg:hidden fixed inset-0 z-30">
<div class="absolute inset-0 bg-black/30" onclick="document.getElementById('mobile-sidebar').classList.add('hidden')"></div>
<div class="absolute right-0 top-0 bottom-0 w-64 bg-white dark:bg-slate-900 shadow-xl overflow-y-auto p-4 space-y-0.5">
<div class="flex justify-between items-center mb-3">
<span class="font-semibold text-sm text-slate-700 dark:text-slate-300">Navigation</span>
<button onclick="document.getElementById('mobile-sidebar').classList.add('hidden')" class="text-slate-400 hover:text-slate-600">&times;</button>
</div>
{sidebar_inner}
</div>
</div>
<!-- Desktop sidebar -->
<nav class="hidden lg:block w-52 flex-shrink-0">
<div class="sticky top-20 space-y-0.5 max-h-[calc(100vh-6rem)] overflow-y-auto pr-2 text-sm">
{sidebar_inner}
</div>
</nav>'''


@app.route("/connector/<name>")
def connector_detail(name: str):
    try:
        sp = _get_spec(name)
    except Exception:
        return _r("Not Found", '<p class="text-center py-16 text-slate-500">Connector not found.</p>'), 404

    actions = sp.get("actions", {})
    meta = get_tool_meta(name)
    import html as _html

    # --- Try README.md rendering first ---
    readme_path = Path(__file__).parent.parent / "src" / "toolsconnector" / "connectors" / name / "README.md"
    # Also check common alternate names (e.g. openai -> openai_connector)
    for alt_name in [name, name.replace("_connector", ""), f"{name}_connector"]:
        alt_path = Path(__file__).parent.parent / "src" / "toolsconnector" / "connectors" / alt_name / "README.md"
        if alt_path.exists():
            readme_path = alt_path
            break

    if readme_path.exists():
        readme_content = readme_path.read_text(encoding="utf-8")

        # Auto-generate actions section
        action_md = ""
        for aname in sorted(actions.keys()):
            act = actions[aname]
            params = act.get("parameters", [])
            scope = act.get("requires_scope", "")
            dangerous = act.get("dangerous", False)
            return_type = act.get("return_type", "Any")

            warn = " :warning:" if dangerous else ""
            scope_text = f" `scope: {scope}`" if scope else ""
            action_md += f"\n### `{aname}`{warn}{scope_text}\n\n"
            action_md += f"{act.get('description', '')}\n\n"

            if params:
                action_md += "| Parameter | Type | Required | Description |\n"
                action_md += "|---|---|---|---|\n"
                for p in params:
                    req = "Yes" if p.get("required") else "No"
                    default = f" (default: `{p['default']}`)" if p.get("default") is not None else ""
                    action_md += f"| `{p['name']}` | `{p.get('type','any')}` | {req} | {p.get('description','')}{default} |\n"
                action_md += "\n"

            action_md += f"**Returns:** `{return_type}`\n\n"

            # Example with real values
            req_params = [p for p in params if p.get("required")]
            opt_params = [p for p in params if not p.get("required")]
            ex_params = req_params + opt_params[:2]
            if ex_params:
                args = ", ".join(f'"{p["name"]}": {_example_value(p)}' for p in ex_params)
                action_md += f'```python\nresult = kit.execute("{name}_{aname}", {{{args}}})\n```\n\n'
            else:
                action_md += f'```python\nresult = kit.execute("{name}_{aname}", {{}})\n```\n\n'

            action_md += "---\n"

        # Inject actions into README
        import re
        if "<!-- ACTIONS_START -->" in readme_content:
            readme_content = re.sub(
                r"<!-- ACTIONS_START -->.*?<!-- ACTIONS_END -->",
                f"<!-- ACTIONS_START -->\n{action_md}\n<!-- ACTIONS_END -->",
                readme_content,
                flags=re.DOTALL,
            )
        else:
            # Append actions at the end if no markers
            readme_content += f"\n\n## Actions\n\n{action_md}"

        # Build sidebar from markdown headings
        headings = re.findall(r"^##\s+(.+)$", readme_content, re.MULTILINE)
        sidebar_links = ""
        for h in headings:
            h_id = h.lower().replace(" ", "-").replace("(", "").replace(")", "")
            sidebar_links += f'<a href="#{h_id}" class="sidebar-link block px-3 py-1.5 rounded text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 font-medium" data-section="{h_id}">{h}</a>\n'

        sidebar_md = f'''<nav class="hidden lg:block w-52 flex-shrink-0">
<div class="sticky top-20 space-y-0.5 max-h-[calc(100vh-6rem)] overflow-y-auto pr-2">
<a href="/connectors" class="block px-3 py-1.5 rounded text-sm text-slate-400 hover:text-slate-600 mb-2">&larr; All Connectors</a>
{sidebar_links}
</div></nav>'''

        # Render with marked.js + custom styles
        escaped_md = json.dumps(readme_content)

        return _r(sp["display_name"], f"""
<div class="flex gap-8">
{sidebar_md}
<div class="flex-1 min-w-0">
<div id="readme-content" class="connector-readme"></div>
</div>
</div>

<style>
.connector-readme {{
    font-family: 'Inter', system-ui, sans-serif;
    line-height: 1.7;
    color: #334155;
}}
.dark .connector-readme {{ color: #cbd5e1; }}
.connector-readme h1 {{
    font-size: 2rem;
    font-weight: 800;
    margin: 0 0 0.3em;
    color: #0f172a;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 0.4em;
}}
.dark .connector-readme h1 {{ color: #f1f5f9; border-color: #334155; }}
.connector-readme blockquote {{
    border-left: 4px solid {meta.get('color', '#6366f1')};
    padding: 0.5em 1em;
    margin: 0 0 1.5em;
    background: #f8fafc;
    border-radius: 0 8px 8px 0;
    color: #64748b;
    font-size: 1.05em;
}}
.dark .connector-readme blockquote {{ background: #1e293b; color: #94a3b8; }}
.connector-readme h2 {{
    font-size: 1.35rem;
    font-weight: 700;
    margin: 2em 0 0.6em;
    padding-bottom: 0.3em;
    border-bottom: 1px solid #e2e8f0;
    color: #1e293b;
}}
.dark .connector-readme h2 {{ color: #e2e8f0; border-color: #334155; }}
.connector-readme h3 {{
    font-size: 1.05rem;
    font-weight: 600;
    margin: 1.5em 0 0.4em;
    color: #334155;
    font-family: 'JetBrains Mono', monospace;
}}
.dark .connector-readme h3 {{ color: #e2e8f0; }}
.connector-readme p {{ margin: 0.5em 0 1em; }}
.connector-readme ul, .connector-readme ol {{
    padding-left: 1.5em;
    margin: 0.5em 0 1em;
}}
.connector-readme li {{ margin: 0.3em 0; }}
.connector-readme code:not(pre code) {{
    background: rgba(99,102,241,0.08);
    padding: 0.15em 0.45em;
    border-radius: 5px;
    font-size: 0.88em;
    font-family: 'JetBrains Mono', monospace;
    color: #4f46e5;
}}
.dark .connector-readme code:not(pre code) {{
    background: rgba(99,102,241,0.15);
    color: #a5b4fc;
}}
.connector-readme pre {{
    background: #0f172a;
    color: #e2e8f0;
    border-radius: 10px;
    padding: 1.2em;
    overflow-x: auto;
    margin: 0.8em 0 1.2em;
    position: relative;
    border: 1px solid #1e293b;
}}
.connector-readme pre code {{
    background: none !important;
    padding: 0 !important;
    color: inherit !important;
    font-size: 0.82em;
    line-height: 1.6;
}}
.connector-readme table {{
    border-collapse: collapse;
    width: 100%;
    margin: 0.8em 0 1.2em;
    font-size: 0.88em;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}}
.dark .connector-readme table {{ border-color: #334155; }}
.connector-readme th {{
    background: #f1f5f9;
    font-weight: 600;
    text-align: left;
    padding: 0.6em 1em;
    font-size: 0.82em;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
}}
.dark .connector-readme th {{ background: #1e293b; color: #94a3b8; }}
.connector-readme td {{
    padding: 0.5em 1em;
    border-top: 1px solid #e2e8f0;
    vertical-align: top;
}}
.dark .connector-readme td {{ border-color: #334155; }}
.connector-readme tr:hover td {{ background: #f8fafc; }}
.dark .connector-readme tr:hover td {{ background: #1e293b; }}
.connector-readme hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 2em 0;
}}
.dark .connector-readme hr {{ border-color: #334155; }}
.connector-readme a {{
    color: #4f46e5;
    text-decoration: none;
}}
.connector-readme a:hover {{ text-decoration: underline; }}
.dark .connector-readme a {{ color: #818cf8; }}
.connector-readme img {{ max-width: 100%; border-radius: 8px; }}
.connector-readme strong {{ font-weight: 700; }}
</style>

<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<script>
marked.setOptions({{
    breaks: false,
    gfm: true,
    highlight: function(code, lang) {{
        if (lang && hljs.getLanguage(lang)) {{
            try {{ return hljs.highlight(code, {{language: lang}}).value; }} catch(e) {{}}
        }}
        return hljs.highlightAuto(code).value;
    }}
}});

// Render markdown
var md = {escaped_md};
var html = marked.parse(md);

// Add IDs to h2 headings for scroll-spy
html = html.replace(/<h2(.*?)>(.*?)<\\/h2>/g, function(match, attrs, text) {{
    var id = text.toLowerCase().replace(/<[^>]+>/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    return '<h2 id="' + id + '" class="scroll-mt-20"' + attrs + '>' + text + '</h2>';
}});

document.getElementById('readme-content').innerHTML = html;

// Add copy buttons to code blocks
document.querySelectorAll('.connector-readme pre').forEach(function(pre) {{
    var btn = document.createElement('button');
    btn.textContent = 'Copy';
    btn.className = 'absolute top-2 right-2 text-[10px] px-2 py-0.5 rounded bg-slate-700 text-slate-400 hover:text-white cursor-pointer';
    btn.onclick = function() {{
        navigator.clipboard.writeText(pre.querySelector('code').textContent.trim());
        btn.textContent = 'Copied!';
        setTimeout(function() {{ btn.textContent = 'Copy'; }}, 1500);
    }};
    pre.style.position = 'relative';
    pre.appendChild(btn);
}});

// Scroll-spy
(function() {{
    var sections = document.querySelectorAll('h2[id]');
    var links = document.querySelectorAll('.sidebar-link');
    var observer = new IntersectionObserver(function(entries) {{
        entries.forEach(function(entry) {{
            if (entry.isIntersecting) {{
                var id = entry.target.id;
                links.forEach(function(l) {{
                    l.classList.remove('bg-b-50','text-b-700');
                    l.classList.add('text-slate-500');
                }});
                var active = document.querySelector('.sidebar-link[data-section="' + id + '"]');
                if (active) {{
                    active.classList.add('bg-b-50','text-b-700');
                    active.classList.remove('text-slate-500');
                }}
            }}
        }});
    }}, {{ rootMargin: '-80px 0px -70% 0px' }});
    sections.forEach(function(s) {{ observer.observe(s); }});
}})();
</script>
""")

    # --- Fallback: generated page (no README.md) ---
    first_action = _best_first_action(actions)
    install_cmd = f'pip install "toolsconnector[{name}]"'

    # Logo
    if meta.get("logo"):
        logo_html = f'<img src="{meta["logo"]}" alt="{sp["display_name"]}" class="w-12 h-12 rounded-xl" onerror="this.style.display=\'none\'">'
    else:
        initials = sp["display_name"][:2].upper()
        logo_html = f'<div class="w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold text-lg" style="background:{meta["color"]}">{initials}</div>'

    # External links as labeled buttons
    _link_cls = "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-xs font-medium text-slate-600 dark:text-slate-400"
    ext_links_html = ""
    if meta.get("website"):
        ext_links_html += f'<a href="{meta["website"]}" target="_blank" rel="noopener" class="{_link_cls}"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3"/></svg>Website</a>'
    if meta.get("docs"):
        ext_links_html += f'<a href="{meta["docs"]}" target="_blank" rel="noopener" class="{_link_cls}"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"/></svg>API Docs</a>'
    if meta.get("github"):
        ext_links_html += f'<a href="{meta["github"]}" target="_blank" rel="noopener" class="{_link_cls}"><svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>GitHub</a>'

    # Auth info footer
    auth_str = ", ".join(meta.get("auth_methods", [])) or "Bearer Token"
    rate_str = meta.get("rate_limit", "")
    pricing_str = meta.get("pricing", "")

    # Auth method badges
    auth_methods = meta.get("auth_methods", []) or ["Bearer Token"]
    auth_badges = " ".join(
        f'<span class="text-xs px-2.5 py-1 rounded-full bg-b-50 dark:bg-b-900/20 text-b-700 dark:text-b-400 font-medium">{m}</span>'
        for m in auth_methods
    )

    # Credentials link
    cred_link_html = ""
    if meta.get("get_credentials_url"):
        cred_link_html = f'<a href="{meta["get_credentials_url"]}" target="_blank" rel="noopener" class="inline-flex items-center gap-1.5 text-sm text-b-600 dark:text-b-400 hover:underline mt-3"><svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>Get credentials</a>'

    # All action sections
    action_sections = "".join(_action_section_html(aname, act, name) for aname, act in sorted(actions.items()))

    # Sidebar
    sidebar = _sidebar_html(actions, name)

    # Quick Start code
    qs_code = _html.escape(f'''from toolsconnector.serve import ToolKit

kit = ToolKit(["{name}"], credentials={{"{name}": "your-token"}})
result = kit.execute("{name}_{first_action}", {{}})
print(result)''')

    # Overview paragraph (merged into hero)
    overview_p = ""
    if meta.get("overview"):
        overview_p = f'<p class="text-sm text-slate-500 dark:text-slate-400 leading-relaxed mt-4">{_html.escape(meta["overview"])}</p>'

    # Prerequisites (compact)
    prereqs_html = ""
    if meta.get("prerequisites"):
        ps = " &middot; ".join(meta["prerequisites"])
        prereqs_html = f'<div class="text-xs text-slate-400 mt-2"><span class="font-medium text-slate-500">Prerequisites:</span> {ps}</div>'

    # Related connectors
    specs = _all_specs()
    related = [(n, s) for n, s in specs.items() if s["category"] == sp["category"] and n != name][:4]
    related_html = ""
    if related:
        related_cards = ""
        for rname, rsp in related:
            rmeta = get_tool_meta(rname)
            if rmeta.get("logo"):
                rlogo = f'<img src="{rmeta["logo"]}" alt="{rsp["display_name"]}" class="w-8 h-8 rounded-lg" onerror="this.style.display=\'none\'">'
            else:
                ri = rsp["display_name"][:2].upper()
                rlogo = f'<div class="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-xs" style="background:{rmeta["color"]}">{ri}</div>'
            rcount = len(rsp.get("actions", {}))
            related_cards += f'''<a href="/connector/{rname}" class="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-b-400 hover:shadow-sm bg-white dark:bg-slate-900 transition-all">
{rlogo}
<div class="min-w-0">
<div class="font-medium text-sm text-slate-800 dark:text-slate-200">{rsp["display_name"]}</div>
<div class="text-xs text-slate-400">{rcount} actions</div>
</div></a>'''
        related_html = f'''
<section id="related" class="scroll-mt-20 mb-8">
<h2 class="text-lg font-semibold text-slate-700 dark:text-slate-300 mb-4">Related Connectors</h2>
<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">{related_cards}</div>
</section>'''

    return _r(sp["display_name"], f"""
<div class="flex gap-8">

<!-- Sidebar -->
{sidebar}

<!-- Content -->
<div class="flex-1 min-w-0">

<!-- Section: Overview -->
<section id="overview" class="scroll-mt-20 mb-8">
<div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" style="border-top:4px solid {meta['color']}">
<div class="p-6 sm:p-8">
<div class="flex items-start gap-5">
{logo_html}
<div class="flex-1 min-w-0">
<div class="flex items-center gap-3 flex-wrap">
<h1 class="text-2xl font-bold text-slate-900 dark:text-white">{sp["display_name"]}</h1>
{f'<span class="text-sm text-slate-400">by {meta["company"]}</span>' if meta.get("company") else ""}
</div>
<p class="text-slate-500 mt-1">{meta.get("tagline") or sp.get("description","")}</p>
<div class="flex items-center gap-2 flex-wrap mt-4">
<span class="text-xs px-2.5 py-1 rounded-full font-medium text-white" style="background:{meta['color']}">{_cat(sp["category"])}</span>
<span class="text-xs px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 font-medium">{sp.get("protocol","rest").upper()}</span>
<span class="text-xs px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 font-medium">{len(actions)} actions</span>
</div>
<div class="flex items-center gap-4 flex-wrap mt-4">{ext_links_html}</div>
</div>
</div>
{overview_p}
</div>
<div class="border-t border-slate-200 dark:border-slate-800 px-6 sm:px-8 py-3 bg-slate-50/50 dark:bg-slate-800/20 flex items-center gap-6 flex-wrap text-sm">
<div><span class="text-slate-400">Auth:</span> <span class="text-slate-700 dark:text-slate-300">{auth_str}</span></div>
{f'<div><span class="text-slate-400">Rate:</span> <span class="font-mono text-xs text-slate-700 dark:text-slate-300">{rate_str}</span></div>' if rate_str else ""}
{f'<div><span class="text-slate-400">Pricing:</span> <span class="text-slate-700 dark:text-slate-300">{pricing_str}</span></div>' if pricing_str else ""}
</div>
</div>
</section>

<!-- Section: Install -->
<section id="install" class="scroll-mt-20 mb-8">
<h2 class="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-4">Install</h2>
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
<div class="flex items-center gap-2 bg-slate-50 dark:bg-slate-800 rounded-lg px-4 py-3">
<code class="text-sm font-mono text-slate-700 dark:text-slate-300 flex-1">{install_cmd}</code>
<button onclick="navigator.clipboard.writeText('{install_cmd}');this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1200)" class="text-xs px-2.5 py-1 rounded bg-b-600 text-white hover:bg-b-700 cursor-pointer font-medium">Copy</button>
</div>
<div class="text-xs text-slate-400 mt-3"><code class="font-mono">export TC_{name.upper()}_CREDENTIALS=your-token</code></div>
{prereqs_html}
{cred_link_html}
<div class="text-xs text-slate-400 mt-3">TypeScript, Go, and Java SDKs coming soon.</div>
</div>
</section>

<!-- Section: Quick Start -->
<section id="quickstart" class="scroll-mt-20 mb-8">
<h2 class="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-4">Quick Start</h2>
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden relative">
<pre class="text-xs bg-slate-900 text-slate-100 p-5 overflow-x-auto"><code class="language-python">{qs_code}</code></pre>
<button onclick="navigator.clipboard.writeText(this.previousElementSibling.querySelector('code').textContent.trim());this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)" class="absolute top-3 right-3 text-[10px] px-2.5 py-1 rounded bg-slate-700 text-slate-400 hover:text-white cursor-pointer">Copy</button>
</div>
<p class="text-xs text-slate-400 mt-2">
Also works with <a href="/docs/mcp-server" class="text-b-600 dark:text-b-400 hover:underline">MCP Server</a>,
<a href="/docs/ai-frameworks" class="text-b-600 dark:text-b-400 hover:underline">OpenAI, Anthropic, Gemini</a>.
</p>
</section>

<!-- Section: Actions -->
<section id="actions" class="scroll-mt-20 mb-8">
<div class="flex items-center justify-between mb-4">
<h2 class="text-lg font-semibold text-slate-800 dark:text-slate-200">Actions <span class="text-slate-400 text-base font-normal">({len(actions)})</span></h2>
<div class="relative"><svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg>
<input type="text" placeholder="Filter actions..." class="pl-9 pr-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-b-500 outline-none w-56" oninput="filterActions(this.value)"></div>
</div>
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
{action_sections}
</div>
</section>

<!-- Section: Authentication -->
<section id="auth" class="scroll-mt-20 mb-8">
<h2 class="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-4">Authentication</h2>
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
<div class="mb-3">
<span class="text-sm text-slate-500 mr-2">Supported:</span>
{auth_badges}
</div>
<div class="bg-slate-50 dark:bg-slate-800/30 rounded-lg px-4 py-3 mt-3">
<code class="text-xs font-mono text-slate-700 dark:text-slate-300">export TC_{name.upper()}_CREDENTIALS=your-token</code>
</div>
{cred_link_html}
</div>
</section>

<!-- Related -->
{related_html}

</div>
</div>

<!-- Scroll-spy + filter JS -->
<script>
(function(){{
  var links = document.querySelectorAll('.sidebar-link');
  var observer = new IntersectionObserver(function(entries) {{
    entries.forEach(function(entry) {{
      if(entry.isIntersecting){{
        var id = entry.target.id;
        links.forEach(function(l) {{
          l.classList.remove('bg-b-50','dark:bg-b-900/20','text-b-700','dark:text-b-400','font-medium');
          if(!l.classList.contains('action-link')) l.classList.add('text-slate-500');
          else l.classList.add('text-slate-400');
        }});
        var active = document.querySelector('.sidebar-link[data-section="'+id+'"]');
        if(active){{
          active.classList.add('bg-b-50','dark:bg-b-900/20','text-b-700','dark:text-b-400');
          if(!active.classList.contains('action-link')) active.classList.add('font-medium');
          active.classList.remove('text-slate-500','text-slate-400');
          if(active.classList.contains('action-link'))
            active.scrollIntoView({{block:'nearest',behavior:'smooth'}});
        }}
      }}
    }});
  }}, {{rootMargin:'-80px 0px -70% 0px'}});
  document.querySelectorAll('section[id]').forEach(function(s) {{ observer.observe(s); }});
}})();

function filterActions(q){{
  q = q.toLowerCase();
  document.querySelectorAll('section[id^="action-"]').forEach(function(s) {{
    var n = s.id.replace('action-','');
    s.style.display = n.includes(q) ? '' : 'none';
  }});
  document.querySelectorAll('.action-link').forEach(function(l) {{
    var n = l.dataset.section.replace('action-','');
    l.style.display = n.includes(q) ? '' : 'none';
  }});
}}
</script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<script>document.querySelectorAll('pre code').forEach(function(b){{ hljs.highlightElement(b); }});</script>""")


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
    # Build system prompt server-side (contains live project data)
    names = list_connectors()
    specs = _all_specs()
    cl = ", ".join(f"{specs[n]['display_name']} ({n})" for n in names)
    cats = set(specs[n]["category"] for n in names)
    total_actions = sum(len(s.get("actions", {})) for s in specs.values())
    cat_list = ", ".join(_cat(c) for c in sorted(cats))
    sys_prompt = (
        "You are the ToolsConnector AI assistant helping developers.\n\n"
        "## What is ToolsConnector?\n"
        f"A universal tool-connection primitive for Python. Standardized way to connect AI agents and apps to {len(names)} third-party tools across {len(cats)} categories. A primitive, not a platform.\n\n"
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
        '## Install: `pip install toolsconnector` or `pip install "toolsconnector[gmail,slack]"`\n\n'
        "## Key Features\n"
        f"{len(names)} connectors, {total_actions} actions, {len(cats)} categories. "
        "OpenAI/Anthropic/Gemini schemas. MCP server. Circuit breakers, retries, timeouts. "
        "Async-first + sync wrappers. JSON Schema validation. Dangerous action filtering. "
        "Multi-tenant. BYOK auth.\n\n"
        "Be concise, technical, include code examples."
    )
    escaped_sys = json.dumps(sys_prompt)

    return _r("AI Assistant", f"""
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<style>
.md-body{{line-height:1.7;font-size:0.875rem}}
.md-body p{{margin:0.5em 0}}
.md-body h1,.md-body h2,.md-body h3{{font-weight:700;margin:0.8em 0 0.4em}}
.md-body h1{{font-size:1.25rem}}.md-body h2{{font-size:1.1rem}}.md-body h3{{font-size:1rem}}
.md-body ul,.md-body ol{{margin:0.4em 0;padding-left:1.5em}}
.md-body li{{margin:0.2em 0}}
.md-body code:not(pre code){{background:rgba(100,116,139,0.15);padding:0.15em 0.4em;border-radius:4px;font-size:0.82em}}
.md-body pre{{background:#1e293b;color:#e2e8f0;border-radius:8px;padding:1em;overflow-x:auto;margin:0.6em 0;position:relative}}
.md-body pre code{{background:none;padding:0;font-size:0.82em}}
.md-body blockquote{{border-left:3px solid #6366f1;padding-left:0.8em;margin:0.5em 0;color:#64748b}}
.md-body table{{border-collapse:collapse;width:100%;margin:0.5em 0;font-size:0.82em}}
.md-body th,.md-body td{{border:1px solid #e2e8f0;padding:0.4em 0.8em;text-align:left}}
.dark .md-body th,.dark .md-body td{{border-color:#334155}}
.md-body th{{background:#f1f5f9;font-weight:600}}.dark .md-body th{{background:#1e293b}}
.md-body a{{color:#4c6ef5;text-decoration:underline}}
.md-body img{{max-width:100%;border-radius:8px;margin:0.5em 0}}
.md-body hr{{border:none;border-top:1px solid #e2e8f0;margin:1em 0}}
.dark .md-body hr{{border-color:#334155}}
.md-body strong{{font-weight:700}}
.copy-btn{{position:absolute;top:8px;right:8px;background:rgba(255,255,255,0.1);border:none;color:#94a3b8;padding:4px 8px;border-radius:4px;cursor:pointer;font-size:11px}}
.copy-btn:hover{{background:rgba(255,255,255,0.2);color:#fff}}
</style>

<h1 class="text-2xl font-bold mb-6">AI Assistant</h1>
<div class="max-w-3xl mx-auto">

<!-- API Key Banner -->
<div id="key-banner" class="hidden mb-4 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-4">
  <div class="flex items-start gap-3">
    <svg class="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z"/></svg>
    <div class="flex-1">
      <h3 class="text-sm font-semibold text-amber-800 dark:text-amber-200">OpenRouter API key required</h3>
      <p class="text-xs text-amber-600 dark:text-amber-400 mt-1 mb-3">Your key is stored only in your browser (localStorage). It never leaves your device — all API calls go directly from your browser to OpenRouter.</p>
      <div class="flex gap-2 items-center">
        <input id="key-input" type="password" placeholder="sk-or-v1-..." class="flex-1 rounded-lg border border-amber-300 dark:border-amber-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-b-500 outline-none" autocomplete="off" spellcheck="false">
        <button onclick="saveKey()" class="px-4 py-2 rounded-lg bg-b-600 hover:bg-b-700 text-white text-sm font-medium flex-shrink-0">Save</button>
      </div>
      <a href="https://openrouter.ai/keys" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-xs text-b-600 dark:text-b-400 hover:underline mt-2">
        <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>
        Get a free API key at openrouter.ai/keys</a>
    </div>
  </div>
</div>

<!-- Key status bar (shown when key is saved) -->
<div id="key-status" class="hidden mb-4 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 px-4 py-2.5 flex items-center justify-between">
  <div class="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
    <span>API key saved <span class="text-emerald-500 dark:text-emerald-500 font-mono text-xs" id="key-preview"></span></span>
  </div>
  <button onclick="clearKey()" class="text-xs text-slate-400 hover:text-red-500 transition-colors">Remove key</button>
</div>

<!-- Chat -->
<div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden flex flex-col" style="height:70vh">
<div id="cm" class="flex-1 overflow-y-auto p-4 space-y-4">
<div class="flex gap-3"><div class="w-8 h-8 rounded-full bg-b-100 dark:bg-b-900/30 flex items-center justify-center text-b-600 dark:text-b-400 flex-shrink-0 text-xs font-bold">TC</div>
<div class="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[80%]"><div class="text-sm md-body"><p>Welcome! Ask me about ToolsConnector — connectors, ToolKit setup, schema generation, or anything else.</p></div></div></div></div>
<div class="border-t border-slate-200 dark:border-slate-800 p-4"><div class="flex gap-2">
<input id="ci" type="text" placeholder="Ask about ToolsConnector..." class="flex-1 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-4 py-2.5 text-sm focus:ring-2 focus:ring-b-500 outline-none" onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendMsg()}}">
<button onclick="sendMsg()" id="sb" class="px-5 py-2.5 rounded-xl bg-b-600 hover:bg-b-700 text-white text-sm font-medium flex-shrink-0">Send</button></div>
<p class="text-xs text-slate-400 mt-2 text-center">Powered by <a href="https://openrouter.ai" target="_blank" class="hover:underline">OpenRouter</a>. Your key stays in your browser. Responses may not always be accurate.</p></div></div></div>

<script>
// ── Key management ──────────────────────────────────────────────────
const KEY_STORAGE = 'tc_openrouter_key';

function getKey() {{ return localStorage.getItem(KEY_STORAGE) || ''; }}

function saveKey() {{
  const inp = document.getElementById('key-input');
  const k = inp.value.trim();
  if (!k) return;
  localStorage.setItem(KEY_STORAGE, k);
  inp.value = '';
  refreshKeyUI();
}}

function clearKey() {{
  localStorage.removeItem(KEY_STORAGE);
  refreshKeyUI();
}}

function refreshKeyUI() {{
  const k = getKey();
  const banner = document.getElementById('key-banner');
  const status = document.getElementById('key-status');
  if (k) {{
    banner.classList.add('hidden');
    status.classList.remove('hidden');
    // Show masked preview: first 10 chars + ···
    document.getElementById('key-preview').textContent = '(' + k.slice(0, 10) + '···)';
  }} else {{
    banner.classList.remove('hidden');
    status.classList.add('hidden');
  }}
}}

// Initialize on page load
refreshKeyUI();

// ── System prompt (generated server-side with live project data) ────
const SYS_PROMPT = {escaped_sys};
const OR_URL = 'https://openrouter.ai/api/v1/chat/completions';
const OR_MODEL = 'qwen/qwen3.6-plus:free';

// ── Markdown rendering ──────────────────────────────────────────────
marked.setOptions({{breaks:true,gfm:true,highlight:function(code,lang){{if(lang&&hljs.getLanguage(lang)){{try{{return hljs.highlight(code,{{language:lang}}).value}}catch(e){{}}}}return hljs.highlightAuto(code).value}}}});

let busy = false;
function esc(s){{ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }}
function renderMd(raw,el){{
  let html = marked.parse(raw);
  html = html.replace(/<pre><code/g, '<pre><button class="copy-btn" onclick="navigator.clipboard.writeText(this.parentElement.querySelector(\\x27code\\x27).textContent);this.textContent=\\x27Copied!\\x27;setTimeout(()=>this.textContent=\\x27Copy\\x27,1500)">Copy</button><code');
  el.innerHTML = html;
  el.querySelectorAll('pre code').forEach(b=>{{ try{{ hljs.highlightElement(b) }}catch(e){{}} }});
}}

// ── Chat (direct browser → OpenRouter, key never leaves the device) ─
async function sendMsg() {{
  if (busy) return;
  const apiKey = getKey();
  if (!apiKey) {{
    document.getElementById('key-banner').classList.remove('hidden');
    document.getElementById('key-input').focus();
    return;
  }}

  const inp = document.getElementById('ci'), msg = inp.value.trim();
  if (!msg) return;
  inp.value = ''; busy = true; document.getElementById('sb').disabled = true;

  const c = document.getElementById('cm');
  c.innerHTML += '<div class="flex gap-3 justify-end"><div class="bg-b-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-[80%]"><div class="text-sm md-body"><p>' + esc(msg) + '</p></div></div><div class="w-8 h-8 rounded-full bg-b-600 flex items-center justify-center text-white flex-shrink-0 text-xs font-bold">You</div></div>';
  const aid = 'a' + Date.now();
  c.innerHTML += '<div class="flex gap-3"><div class="w-8 h-8 rounded-full bg-b-100 dark:bg-b-900/30 flex items-center justify-center text-b-600 dark:text-b-400 flex-shrink-0 text-xs font-bold">TC</div><div class="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[80%] w-full"><div class="text-sm md-body" id="' + aid + '"><span class="text-slate-400 animate-pulse">Thinking...</span></div></div></div>';
  c.scrollTop = c.scrollHeight;

  let raw = '';
  try {{
    const r = await fetch(OR_URL, {{
      method: 'POST',
      headers: {{
        'Authorization': 'Bearer ' + apiKey,
        'Content-Type': 'application/json',
        'HTTP-Referer': location.origin,
        'X-Title': 'ToolsConnector',
      }},
      body: JSON.stringify({{
        model: OR_MODEL,
        messages: [
          {{ role: 'system', content: SYS_PROMPT }},
          {{ role: 'user', content: msg }},
        ],
        stream: true,
      }}),
    }});

    if (!r.ok) {{
      const errBody = await r.text();
      const el = document.getElementById(aid);
      if (r.status === 401 || r.status === 403) {{
        el.innerHTML = '<p class="text-red-500">Invalid API key. Please check your OpenRouter key and try again.</p>';
        clearKey();
      }} else {{
        el.innerHTML = '<p class="text-red-500">API error (' + r.status + '): ' + esc(errBody.slice(0, 200)) + '</p>';
      }}
      busy = false; document.getElementById('sb').disabled = false;
      return;
    }}

    const rd = r.body.getReader(), dc = new TextDecoder(), el = document.getElementById(aid);
    let buf = '';
    while (true) {{
      const {{ done, value }} = await rd.read();
      if (done) break;
      buf += dc.decode(value, {{ stream: true }});
      const ls = buf.split(String.fromCharCode(10));
      buf = ls.pop() || '';
      for (const l of ls) {{
        const lt = l.trim();
        if (lt.startsWith('data: ')) {{
          const d = lt.slice(6);
          if (d === '[DONE]') break;
          try {{
            const p = JSON.parse(d);
            const delta = p.choices && p.choices[0] && p.choices[0].delta;
            if (delta && delta.content) {{ raw += delta.content; renderMd(raw, el); }}
          }} catch(e) {{}}
        }}
      }}
      c.scrollTop = c.scrollHeight;
    }}
    if (!raw) {{ el.innerHTML = '<p class="text-slate-400">No response received. Try again.</p>'; }}
  }} catch(e) {{
    const el = document.getElementById(aid);
    if (el) el.innerHTML = '<p class="text-red-500">Error: ' + esc(e.message) + '</p>';
  }}
  busy = false; document.getElementById('sb').disabled = false;
}}
</script>""")


# /api/chat removed — AI assistant now calls OpenRouter directly from the
# browser using the user's own key stored in localStorage.  The key never
# touches this server.


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
        # Fallback: use marked.js on the client side. The raw string is passed
        # to JS via json.dumps(raw) below — which handles JSON escaping. No need
        # to pre-escape via html.escape (would double-encode &/< in the markdown).
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
