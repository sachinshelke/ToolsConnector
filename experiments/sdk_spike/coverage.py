"""Full-scale coverage classifier — does the declarative binding hold beyond the 3 hardest?

Statically scans EVERY @action method in ALL connectors and buckets each by whether
a SINGLE declarative ActionBinding (the spike's vocabulary) could express it, or
whether it needs a true imperative escape hatch.

The classification is intentionally TRANSPARENT and conservative: it keys off
objective structural "smells" an AST can detect with high precision, and prints
the full reason for every flagged action so the escape-hatch % is auditable rather
than a black box. It does NOT claim to be a compiler — it produces a defensible
estimate with an explicit uncertainty band (the REVIEW bucket).

Buckets:
  DECLARATIVE      single upstream request, no imperative smell — a 1:1 ActionBinding.
  REVIEW           a soft smell (manual query-string build, response-header logic,
                   or zero detected requests) — almost always declarable with a
                   small vocab addition, but worth a human glance.
  ESCAPE_HATCH     a HARD smell a single binding cannot express:
                     • ≥2 sequential upstream requests (orchestration)
                     • a loop/await-for issuing requests (fan-out / polling)
                     • inline crypto/signing/id-gen in the body (computed material)

Run:  .venv/bin/python -m experiments.sdk_spike.coverage
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONNECTORS = ROOT / "src" / "toolsconnector" / "connectors"

HTTP_VERBS = {"get", "post", "put", "patch", "delete", "head", "options"}
CRYPTO_ROOTS = {"hashlib", "hmac", "base64", "secrets", "uuid"}


def is_action(fn: ast.AST) -> bool:
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for dec in fn.decorator_list:
        call = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(call, ast.Name) and call.id == "action":
            return True
        if isinstance(call, ast.Attribute) and call.attr == "action":
            return True
    return False


def _is_http_call(node: ast.AST) -> bool:
    """An awaited call to a request verb / *request helper on self.<…>."""
    if not (isinstance(node, ast.Await) and isinstance(node.value, ast.Call)):
        return False
    func = node.value.func
    if not isinstance(func, ast.Attribute):
        return False
    attr = func.attr
    return attr in HTTP_VERBS or attr == "request" or attr.endswith("_request") or attr == "_request"


def _crypto_root(node: ast.AST) -> str | None:
    """Return the module name if this is a crypto/id call like hashlib.sha256(...)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        v = node.func.value
        if isinstance(v, ast.Name) and v.id in CRYPTO_ROOTS:
            return v.id
    return None


def classify(fn: ast.AST) -> tuple[str, list[str]]:
    http_calls = 0
    loop_request = False
    crypto: set[str] = set()
    manual_qs = False
    header_logic = False

    # loop bodies that contain an http call
    for node in ast.walk(fn):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            if any(_is_http_call(c) for c in ast.walk(node)):
                loop_request = True
        if _is_http_call(node):
            http_calls += 1
        root = _crypto_root(node)
        if root:
            crypto.add(root)
        # manual query-string / bracket assembly
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            manual_qs = True
        if isinstance(node, ast.Attribute) and node.attr == "headers":
            header_logic = True

    hard: list[str] = []
    if http_calls >= 2:
        hard.append(f"{http_calls} sequential upstream requests (orchestration)")
    if loop_request:
        hard.append("loop issues upstream requests (fan-out/polling)")
    if crypto:
        hard.append(f"inline {'/'.join(sorted(crypto))} in body (computed request material)")
    if hard:
        return "ESCAPE_HATCH", hard

    soft: list[str] = []
    if manual_qs:
        soft.append("manual query-string build (.join) — likely a serialization style")
    if header_logic:
        soft.append("reads response headers in body — pagination/limit logic")
    if http_calls == 0:
        soft.append("no upstream request detected (composite or local-only)")
    if soft:
        return "REVIEW", soft
    return "DECLARATIVE", []


def main() -> int:
    per_conn: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    escape: list[tuple[str, str, list[str]]] = []
    review: list[tuple[str, str, list[str]]] = []
    total = 0

    for py in sorted(CONNECTORS.rglob("*.py")):
        rel = py.relative_to(CONNECTORS)
        conn = rel.parts[0]
        if conn.startswith("_") or py.name in {"__init__.py", "types.py"}:
            # _aws shared signer etc.; types have no actions
            if conn.startswith("_"):
                continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if is_action(node):
                total += 1
                bucket, reasons = classify(node)
                per_conn[conn][bucket] += 1
                if bucket == "ESCAPE_HATCH":
                    escape.append((conn, node.name, reasons))
                elif bucket == "REVIEW":
                    review.append((conn, node.name, reasons))

    decl = sum(c.get("DECLARATIVE", 0) for c in per_conn.values())
    rev = sum(c.get("REVIEW", 0) for c in per_conn.values())
    esc = sum(c.get("ESCAPE_HATCH", 0) for c in per_conn.values())

    def pct(n):
        return f"{100 * n / total:.1f}%" if total else "—"

    print("\n" + "=" * 74)
    print("  DECLARATIVE COVERAGE ACROSS ALL CONNECTORS  (static AST classifier)")
    print("=" * 74)
    print(f"  Connectors scanned : {len(per_conn)}")
    print(f"  @action methods    : {total}")
    print("-" * 74)
    print(f"  DECLARATIVE   {decl:>4}  ({pct(decl)})  — 1:1 ActionBinding, no imperative smell")
    print(f"  REVIEW        {rev:>4}  ({pct(rev)})  — soft smell, likely declarable w/ vocab add")
    print(f"  ESCAPE_HATCH  {esc:>4}  ({pct(esc)})  — needs an imperative override")
    print("-" * 74)
    lo = pct(decl)
    hi = pct(decl + rev)
    print(f"  => Declaratively expressible: between {lo} (hard floor) and {hi} (incl. REVIEW)")
    print(f"  => True escape-hatch ceiling: {pct(esc)}  ({esc}/{total} actions)")

    print(f"\n  ESCAPE_HATCH actions ({len(escape)}) — every one, with reason:")
    for conn, name, reasons in sorted(escape):
        print(f"    • {conn}.{name}: {'; '.join(reasons)}")

    # group escape reasons
    rc: dict[str, int] = defaultdict(int)
    for _, _, reasons in escape:
        for r in reasons:
            key = r.split(" (")[0].split(" —")[0]
            key = "".join(ch for ch in key if not ch.isdigit()).replace("  ", " ").strip()
            rc[key] += 1
    print("\n  Escape-hatch reason histogram:")
    for k, v in sorted(rc.items(), key=lambda kv: -kv[1]):
        print(f"    {v:>3}  {k}")

    print(f"\n  REVIEW sample ({min(len(review), 12)} of {len(review)}):")
    for conn, name, reasons in review[:12]:
        print(f"    • {conn}.{name}: {'; '.join(reasons)}")
    print("=" * 74 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
