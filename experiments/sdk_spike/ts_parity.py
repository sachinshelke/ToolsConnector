"""Cross-language parity: the GENERATED TypeScript runtime must build the same
requests as the Python executor, from the same bindings.

Runs `node ts/src/parity.ts` (Node 23 type-strips & executes the generated SDK),
then diffs each request against Python's build_request.

Run:  .venv/bin/python -m experiments.sdk_spike.ts_parity
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl

from .executor import build_request, next_request
from .parity import MATRIX, PAGI
from .specs import ALL

PARITY_TS = Path(__file__).resolve().parent / "ts" / "src" / "parity.ts"
GREEN, RED, RST = "\033[32m", "\033[31m", "\033[0m"


def run_node() -> dict:
    out = subprocess.run(["node", str(PARITY_TS)], capture_output=True, text=True)
    if out.returncode != 0:
        print("node parity.ts failed:\n" + out.stderr)
        sys.exit(2)
    rows = [json.loads(line) for line in out.stdout.splitlines() if line.strip().startswith("{")]
    return {(r["kind"], r["connector"], r["action"]): r for r in rows}


def body_eq(py_bytes: bytes, ts_str, encoding: str) -> bool:
    py_bytes = py_bytes or b""
    ts_str = ts_str or ""
    if not py_bytes and not ts_str:
        return True
    if encoding == "form":
        return sorted(parse_qsl(py_bytes.decode())) == sorted(parse_qsl(ts_str))
    return json.loads(py_bytes or b"{}") == json.loads(ts_str or "{}")


def _cmp(pr, tr, ep, enc) -> list[str]:
    """Diff a Python httpx.Request against a TS canonical-request row."""
    d: list[str] = []
    if pr.method != tr["method"]:
        d.append(f"method {pr.method!r} != {tr['method']!r}")
    if pr.url.host != tr["host"]:
        d.append(f"host {pr.url.host!r} != {tr['host']!r}")
    if pr.url.path != tr["path"]:
        d.append(f"path {pr.url.path!r} != {tr['path']!r}")
    pq = sorted(pr.url.params.multi_items())
    tq = sorted((k, v) for k, v in tr["query"])
    if pq != tq:
        d.append(f"query\n      py={pq}\n      ts={tq}")
    if not body_eq(pr.content, tr["body"], enc):
        d.append(f"body\n      py={pr.content!r}\n      ts={tr['body']!r}")
    pa = pr.headers.get(ep.auth_header)
    if pa != tr["auth"]:
        d.append(f"auth[{ep.auth_header}] {pa!r} != {tr['auth']!r}")
    return d


def main() -> int:
    ts = run_node()
    results: list[tuple[str, str, bool, list[str]]] = []

    # First-request parity.
    for cname, (cred, actions) in MATRIX.items():
        conn = ALL[cname]
        for action, kwargs in actions:
            a = conn.actions[action]
            ep = conn.endpoints[a.endpoint]
            enc = a.body_encoding or ep.encoding
            pr = build_request(conn, action, kwargs, cred)
            tr = ts.get(("first", cname, action))
            d = ["missing in TS output"] if tr is None else _cmp(pr, tr, ep, enc)
            results.append((cname, action, not d, d))

    # Next-page parity: the TS nextRequest must match the Python next_request.
    for cname, cred, action, first_args, body, headers in PAGI:
        conn = ALL[cname]
        a = conn.actions[action]
        ep = conn.endpoints[a.endpoint]
        enc = a.body_encoding or ep.encoding
        pr = next_request(conn, action, first_args, cred, body=body, headers=headers)
        tr = ts.get(("next", cname, action))
        label = f"{action} →next"
        if tr is None:
            d = ["missing in TS output"]
        elif tr.get("none"):
            d = [] if pr is None else ["TS returned no next request but Python did"]
        elif pr is None:
            d = ["Python returned no next request but TS did"]
        else:
            d = _cmp(pr, tr, ep, enc)
        results.append((cname, label, not d, d))

    print("\n" + "=" * 72)
    print("  PYTHON executor  vs  GENERATED TYPESCRIPT runtime  (identical bindings)")
    print("=" * 72)
    npass = 0
    for cname, action, ok, d in results:
        print(f"  {(GREEN + 'PASS' + RST) if ok else (RED + 'FAIL' + RST)}  {cname}.{action}")
        for line in d:
            print(f"        - {line}")
        npass += ok
    print("-" * 72)
    print(f"  {npass}/{len(results)} requests byte-identical across Python and TypeScript")
    print("-" * 72 + "\n")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
