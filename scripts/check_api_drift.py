"""Tier 1 API freshness monitor -- detect drift in Google APIs vs baselines.

Fetches the machine-readable Google Discovery Document for each Tier 1 (Google)
connector, normalizes it to the surface we care about (methods, parameters,
scopes, schemas, version/revision), and diffs it against a committed baseline
snapshot under ``.agent/api-baselines/``. On semantic drift it prints a report
and an impact assessment (which changes touch scopes WE declare) and exits 1 so
CI can open an issue.

    # refresh baselines (first run / after reviewing a change)
    python scripts/check_api_drift.py --update-baselines

    # check for drift (CI); exit 1 on semantic drift
    python scripts/check_api_drift.py
    python scripts/check_api_drift.py --connector gmail

Design notes:
* The pure functions (:func:`normalize`, :func:`diff`, :func:`assess_impact`)
  have **no third-party dependency** -- only :func:`fetch_discovery` imports
  ``httpx``, lazily. This keeps the unit tests network- and dependency-free.
* A ``revision`` bump with no surface change is NOT drift (Google bumps it for
  doc-only edits, which we strip). Only method/param/scope/schema/version
  changes count.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Registry -- the 6 Tier 1 (Google) connectors.
#
# ``used_scopes`` mirrors each connector's declared scopes (verified against the
# connector source). It powers the impact map. TODO(freshness): source these
# from the connector specs directly so there is a single source of truth.
# ---------------------------------------------------------------------------

_SCOPE = "https://www.googleapis.com/auth/"

REGISTRY: dict[str, dict[str, Any]] = {
    "gmail": {
        "api": "gmail",
        "version": "v1",
        "url": "https://www.googleapis.com/discovery/v1/apis/gmail/v1/rest",
        "used_scopes": [
            _SCOPE + "gmail.readonly",
            _SCOPE + "gmail.send",
            _SCOPE + "gmail.modify",
            _SCOPE + "gmail.labels",
        ],
    },
    "gcalendar": {
        "api": "calendar",
        "version": "v3",
        "url": "https://www.googleapis.com/discovery/v1/apis/calendar/v3/rest",
        "used_scopes": [_SCOPE + "calendar", _SCOPE + "calendar.readonly"],
    },
    "gdrive": {
        "api": "drive",
        "version": "v3",
        "url": "https://www.googleapis.com/discovery/v1/apis/drive/v3/rest",
        "used_scopes": [_SCOPE + "drive", _SCOPE + "drive.file"],
    },
    "gdocs": {
        "api": "docs",
        "version": "v1",
        "url": "https://www.googleapis.com/discovery/v1/apis/docs/v1/rest",
        "used_scopes": [_SCOPE + "documents", _SCOPE + "documents.readonly"],
    },
    "gsheets": {
        "api": "sheets",
        "version": "v4",
        "url": "https://www.googleapis.com/discovery/v1/apis/sheets/v4/rest",
        "used_scopes": [_SCOPE + "spreadsheets", _SCOPE + "spreadsheets.readonly"],
    },
    "gtasks": {
        "api": "tasks",
        "version": "v1",
        "url": "https://www.googleapis.com/discovery/v1/apis/tasks/v1/rest",
        "used_scopes": [_SCOPE + "tasks", _SCOPE + "tasks.readonly"],
    },
}

BASELINE_DIR = Path(__file__).resolve().parent.parent / ".agent" / "api-baselines"


# ---------------------------------------------------------------------------
# Pure core -- no third-party deps.
# ---------------------------------------------------------------------------


def _collect_methods(resources: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Recursively collect every method from a Discovery ``resources`` tree.

    Returns a flat ``{method_id: {path, httpMethod, scopes, parameters}}`` map,
    keyed by the method's fully-qualified ``id`` (e.g. ``tasks.tasks.list``).
    """
    out: dict[str, Any] = {}
    for res in (resources or {}).values():
        for method in (res.get("methods") or {}).values():
            mid = method.get("id")
            if not mid:
                continue
            out[mid] = {
                "path": method.get("path"),
                "httpMethod": method.get("httpMethod"),
                "scopes": sorted(method.get("scopes") or []),
                "parameters": {
                    pname: {
                        "type": param.get("type"),
                        "location": param.get("location"),
                        "required": bool(param.get("required", False)),
                    }
                    for pname, param in (method.get("parameters") or {}).items()
                },
            }
        out.update(_collect_methods(res.get("resources")))
    return out


def normalize(doc: dict[str, Any]) -> dict[str, Any]:
    """Reduce a raw Discovery Document to the surface we track.

    Strips noise (descriptions, docs URLs, etag, icons) so a diff reflects real
    API-surface change, not documentation edits.
    """
    methods = _collect_methods(doc.get("resources"))
    # A few APIs expose top-level methods too.
    for method in (doc.get("methods") or {}).values():
        mid = method.get("id")
        if mid:
            methods[mid] = {
                "path": method.get("path"),
                "httpMethod": method.get("httpMethod"),
                "scopes": sorted(method.get("scopes") or []),
                "parameters": {
                    pname: {
                        "type": param.get("type"),
                        "location": param.get("location"),
                        "required": bool(param.get("required", False)),
                    }
                    for pname, param in (method.get("parameters") or {}).items()
                },
            }

    schemas = {
        name: sorted((schema.get("properties") or {}).keys())
        for name, schema in (doc.get("schemas") or {}).items()
    }

    method_scopes = {sc for m in methods.values() for sc in m["scopes"]}
    auth_scopes = set((doc.get("auth", {}).get("oauth2", {}).get("scopes") or {}).keys())

    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "version": doc.get("version"),
        "revision": doc.get("revision"),
        "methods": methods,
        "schemas": schemas,
        "scopes": sorted(method_scopes | auth_scopes),
    }


def _diff_method(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Diff two normalized methods; empty dict means unchanged."""
    changes: dict[str, Any] = {}
    if old.get("path") != new.get("path"):
        changes["path"] = [old.get("path"), new.get("path")]
    if old.get("httpMethod") != new.get("httpMethod"):
        changes["httpMethod"] = [old.get("httpMethod"), new.get("httpMethod")]

    old_scopes, new_scopes = set(old.get("scopes") or []), set(new.get("scopes") or [])
    if old_scopes != new_scopes:
        changes["scopes_added"] = sorted(new_scopes - old_scopes)
        changes["scopes_removed"] = sorted(old_scopes - new_scopes)

    old_p, new_p = old.get("parameters") or {}, new.get("parameters") or {}
    added = sorted(set(new_p) - set(old_p))
    removed = sorted(set(old_p) - set(new_p))
    changed = {p: [old_p[p], new_p[p]] for p in sorted(set(old_p) & set(new_p)) if old_p[p] != new_p[p]}
    if added:
        changes["params_added"] = added
    if removed:
        changes["params_removed"] = removed
    if changed:
        changes["params_changed"] = changed
    return changes


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Structured diff between two normalized Discovery snapshots."""
    report: dict[str, Any] = {
        "id": new.get("id"),
        "version_change": None,
        "revision_change": None,
        "methods_added": [],
        "methods_removed": [],
        "methods_changed": {},
        "schemas_added": [],
        "schemas_removed": [],
        "schemas_changed": {},
        "scopes_added": [],
        "scopes_removed": [],
    }

    if old.get("version") != new.get("version"):
        report["version_change"] = [old.get("version"), new.get("version")]
    if old.get("revision") != new.get("revision"):
        report["revision_change"] = [old.get("revision"), new.get("revision")]

    old_m, new_m = old.get("methods") or {}, new.get("methods") or {}
    report["methods_added"] = sorted(set(new_m) - set(old_m))
    report["methods_removed"] = sorted(set(old_m) - set(new_m))
    for mid in sorted(set(old_m) & set(new_m)):
        changes = _diff_method(old_m[mid], new_m[mid])
        if changes:
            report["methods_changed"][mid] = changes

    old_s, new_s = old.get("schemas") or {}, new.get("schemas") or {}
    report["schemas_added"] = sorted(set(new_s) - set(old_s))
    report["schemas_removed"] = sorted(set(old_s) - set(new_s))
    for name in sorted(set(old_s) & set(new_s)):
        fields_added = sorted(set(new_s[name]) - set(old_s[name]))
        fields_removed = sorted(set(old_s[name]) - set(new_s[name]))
        if fields_added or fields_removed:
            report["schemas_changed"][name] = {
                "fields_added": fields_added,
                "fields_removed": fields_removed,
            }

    old_sc, new_sc = set(old.get("scopes") or []), set(new.get("scopes") or [])
    report["scopes_added"] = sorted(new_sc - old_sc)
    report["scopes_removed"] = sorted(old_sc - new_sc)
    return report


def has_semantic_drift(report: dict[str, Any]) -> bool:
    """True if the report contains any API-surface change (revision-only is not drift)."""
    return bool(
        report["version_change"]
        or report["methods_added"]
        or report["methods_removed"]
        or report["methods_changed"]
        or report["schemas_added"]
        or report["schemas_removed"]
        or report["schemas_changed"]
        or report["scopes_added"]
        or report["scopes_removed"]
    )


def assess_impact(report: dict[str, Any], used_scopes: list[str]) -> list[dict[str, str]]:
    """Flag drift that touches what WE expose. Returns [{level, message}]."""
    used = set(used_scopes)
    findings: list[dict[str, str]] = []

    if report["version_change"]:
        old, new = report["version_change"]
        findings.append({"level": "HIGH", "message": f"API version changed {old} -> {new} (likely breaking)"})

    hit_removed = sorted(set(report["scopes_removed"]) & used)
    for scope in hit_removed:
        findings.append({"level": "HIGH", "message": f"Scope WE declare was removed from the API: {scope}"})

    for mid, changes in report["methods_changed"].items():
        if set(changes.get("scopes_removed") or []) & used:
            findings.append({"level": "HIGH", "message": f"Method {mid} dropped a scope we declare"})
        if changes.get("params_removed"):
            findings.append({"level": "MEDIUM", "message": f"Method {mid} removed params: {changes['params_removed']}"})
        if "path" in changes:
            findings.append({"level": "MEDIUM", "message": f"Method {mid} path changed: {changes['path']}"})

    for mid in report["methods_removed"]:
        findings.append({"level": "MEDIUM", "message": f"Method removed: {mid} (check if we use it)"})

    return findings


def render(name: str, report: dict[str, Any], impact: list[dict[str, str]]) -> str:
    """Human-readable one-connector drift summary."""
    lines = [f"### {name} ({report['id']})"]
    if report["version_change"]:
        lines.append(f"- VERSION: {report['version_change'][0]} -> {report['version_change'][1]}")
    if report["revision_change"]:
        lines.append(f"- revision: {report['revision_change'][0]} -> {report['revision_change'][1]}")
    for label, key in [
        ("methods added", "methods_added"),
        ("methods removed", "methods_removed"),
        ("scopes added", "scopes_added"),
        ("scopes removed", "scopes_removed"),
        ("schemas added", "schemas_added"),
        ("schemas removed", "schemas_removed"),
    ]:
        if report[key]:
            lines.append(f"- {label} ({len(report[key])}): {', '.join(report[key])}")
    if report["methods_changed"]:
        lines.append(f"- methods changed ({len(report['methods_changed'])}): {', '.join(sorted(report['methods_changed']))}")
    if report["schemas_changed"]:
        lines.append(f"- schemas changed ({len(report['schemas_changed'])}): {', '.join(sorted(report['schemas_changed']))}")
    if impact:
        lines.append("- IMPACT:")
        lines.extend(f"    [{f['level']}] {f['message']}" for f in impact)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# I/O -- fetch (lazy httpx) + baseline read/write.
# ---------------------------------------------------------------------------


def fetch_discovery(url: str) -> dict[str, Any]:
    """Fetch a raw Discovery Document. Imports httpx lazily."""
    import httpx

    resp = httpx.get(url, timeout=30.0, headers={"Accept": "application/json"}, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def baseline_path(cfg: dict[str, Any]) -> Path:
    return BASELINE_DIR / f"{cfg['api']}.{cfg['version']}.json"


def load_baseline(cfg: dict[str, Any]) -> Optional[dict[str, Any]]:
    path = baseline_path(cfg)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_baseline(cfg: dict[str, Any], snapshot: dict[str, Any]) -> Path:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    path = baseline_path(cfg)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _selected(connector: Optional[str]) -> dict[str, dict[str, Any]]:
    if connector:
        if connector not in REGISTRY:
            raise SystemExit(f"Unknown connector {connector!r}. Known: {', '.join(REGISTRY)}")
        return {connector: REGISTRY[connector]}
    return REGISTRY


def cmd_update(connector: Optional[str]) -> int:
    for name, cfg in _selected(connector).items():
        snapshot = normalize(fetch_discovery(cfg["url"]))
        path = write_baseline(cfg, snapshot)
        print(f"updated baseline: {name} -> {path.relative_to(BASELINE_DIR.parent.parent)} "
              f"({snapshot['version']} rev {snapshot['revision']})")
    return 0


def cmd_check(connector: Optional[str]) -> int:
    drifted = False
    missing = False
    for name, cfg in _selected(connector).items():
        baseline = load_baseline(cfg)
        if baseline is None:
            print(f"[{name}] NO BASELINE -- run --update-baselines first")
            missing = True
            continue
        current = normalize(fetch_discovery(cfg["url"]))
        report = diff(baseline, current)
        if has_semantic_drift(report):
            drifted = True
            impact = assess_impact(report, cfg["used_scopes"])
            print(render(name, report, impact))
            print()
        elif report["revision_change"]:
            print(f"[{name}] revision bump only, no surface change "
                  f"({report['revision_change'][0]} -> {report['revision_change'][1]})")
        else:
            print(f"[{name}] up to date ({current['version']} rev {current['revision']})")

    if missing:
        return 2
    return 1 if drifted else 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tier 1 (Google) API drift monitor")
    parser.add_argument("--update-baselines", action="store_true", help="fetch and (re)write baselines")
    parser.add_argument("--connector", help="limit to one connector (e.g. gmail)")
    args = parser.parse_args(argv)

    if args.update_baselines:
        return cmd_update(args.connector)
    return cmd_check(args.connector)


if __name__ == "__main__":
    sys.exit(main())
