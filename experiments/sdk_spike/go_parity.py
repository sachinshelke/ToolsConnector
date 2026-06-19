"""Cross-language parity: the GENERATED Go runtime must build the same requests
as the Python executor, from the same bindings.

Runs ``go run ./cmd/parity`` (the Go harness replays the MATRIX/PAGI through the
generated bindings + hand-written runtime), then diffs each canonical request
against Python's build_request / next_request — byte-for-byte.

Run:  .venv/bin/python -m experiments.sdk_spike.go_parity
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

GO_DIR = Path(__file__).resolve().parent / "go"
GREEN, RED, RST = "\033[32m", "\033[31m", "\033[0m"


def run_go() -> dict:
    out = subprocess.run(
        ["go", "run", "./cmd/parity"], cwd=GO_DIR, capture_output=True, text=True
    )
    if out.returncode != 0:
        print("go parity harness failed:\n" + out.stderr)
        sys.exit(2)
    rows = [json.loads(line) for line in out.stdout.splitlines() if line.strip().startswith("{")]
    return {(r["kind"], r["connector"], r["action"]): r for r in rows}


def body_eq(py_bytes: bytes, go_str, encoding: str) -> bool:
    py_bytes = py_bytes or b""
    go_str = go_str or ""
    if not py_bytes and not go_str:
        return True
    if encoding == "form":
        return sorted(parse_qsl(py_bytes.decode())) == sorted(parse_qsl(go_str))
    return json.loads(py_bytes or b"{}") == json.loads(go_str or "{}")


def _cmp(pr, gr, ep, enc) -> list[str]:
    """Diff a Python httpx.Request against a Go canonical-request row."""
    d: list[str] = []
    if pr.method != gr["method"]:
        d.append(f"method {pr.method!r} != {gr['method']!r}")
    if pr.url.host != gr["host"]:
        d.append(f"host {pr.url.host!r} != {gr['host']!r}")
    if pr.url.path != gr["path"]:
        d.append(f"path {pr.url.path!r} != {gr['path']!r}")
    pq = sorted(pr.url.params.multi_items())
    gq = sorted((k, v) for k, v in gr["query"])
    if pq != gq:
        d.append(f"query\n      py={pq}\n      go={gq}")
    if not body_eq(pr.content, gr["body"], enc):
        d.append(f"body\n      py={pr.content!r}\n      go={gr['body']!r}")
    pa = pr.headers.get(ep.auth_header)
    if pa != gr["auth"]:
        d.append(f"auth[{ep.auth_header}] {pa!r} != {gr['auth']!r}")
    return d


def main() -> int:
    go = run_go()
    results: list[tuple[str, str, bool, list[str]]] = []

    # First-request parity.
    for cname, (cred, actions) in MATRIX.items():
        conn = ALL[cname]
        for action, kwargs in actions:
            a = conn.actions[action]
            ep = conn.endpoints[a.endpoint]
            enc = a.body_encoding or ep.encoding
            pr = build_request(conn, action, kwargs, cred)
            gr = go.get(("first", cname, action))
            d = ["missing in Go output"] if gr is None else _cmp(pr, gr, ep, enc)
            results.append((cname, action, not d, d))

    # Next-page parity: the Go NextRequest must match the Python next_request.
    for cname, cred, action, first_args, body, headers in PAGI:
        conn = ALL[cname]
        a = conn.actions[action]
        ep = conn.endpoints[a.endpoint]
        enc = a.body_encoding or ep.encoding
        pr = next_request(conn, action, first_args, cred, body=body, headers=headers)
        gr = go.get(("next", cname, action))
        label = f"{action} →next"
        if gr is None:
            d = ["missing in Go output"]
        elif gr.get("none"):
            d = [] if pr is None else ["Go returned no next request but Python did"]
        elif pr is None:
            d = ["Python returned no next request but Go did"]
        else:
            d = _cmp(pr, gr, ep, enc)
        results.append((cname, label, not d, d))

    print("\n" + "=" * 72)
    print("  PYTHON executor  vs  GENERATED GO runtime  (identical bindings)")
    print("=" * 72)
    npass = 0
    for cname, action, ok, d in results:
        print(f"  {(GREEN + 'PASS' + RST) if ok else (RED + 'FAIL' + RST)}  {cname}.{action}")
        for line in d:
            print(f"        - {line}")
        npass += ok
    print("-" * 72)
    print(f"  {npass}/{len(results)} requests byte-identical across Python and Go")
    print("-" * 72 + "\n")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
