"""Cross-language SDK parity gate.

For one connector, drives the SAME action matrix through all three language
runtimes and asserts they emit the SAME request:

  Python : toolsconnector.spec.executor.build_request   (the reference)
  TS     : sdks/typescript/src/runtime.ts  buildRequest (via Node type-strip)
  Go     : sdks/go/runtime.go               BuildRequest (via go test)

Comparison is canonical: method + host + path + sorted query + PARSED JSON body
+ auth header. (Bodies are compared parsed, not byte-for-byte, because Go's
encoding/json sorts map keys — the request is functionally identical regardless.)

Run:  .venv/bin/python scripts/sdk_parity.py notion
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))  # notion_binding_parity, slack_binding_parity
sys.path.insert(0, str(ROOT))  # experiments.sdk_spike.parity (Stripe/GitHub matrices)

from toolsconnector.spec.executor import build_request  # noqa: E402

# connector -> (binding-module, const, matrix-source, credential)
# matrix-source: a scripts module exposing MATRIX (list of (action, args)), or
# the sentinel "spike" to pull the matrix + cred from experiments/sdk_spike/parity.
CONNECTORS = {
    "notion": (
        "toolsconnector.connectors.notion.binding",
        "NOTION_BINDING",
        "notion_binding_parity",
        "secret_fake_integration_token",
    ),
    "slack": (
        "toolsconnector.connectors.slack.binding",
        "SLACK_BINDING",
        "slack_binding_parity",
        "xoxb-fake-bot-token",
    ),
    "stripe": ("toolsconnector.connectors.stripe.binding", "STRIPE_BINDING", "spike", None),
    "github": ("toolsconnector.connectors.github.binding", "GITHUB_BINDING", "spike", None),
}

GREEN, RED, RST = "\033[32m", "\033[31m", "\033[0m"


def _parse_body(body):
    """Parse a body for comparison — JSON (Notion/Slack/GitHub) or form (Stripe).

    Accepts bytes (Python httpx.Request.content) or str (TS/Go harness output).
    Form bodies are returned as a sorted (key, value) list so cross-language
    ordering never matters.
    """
    if not body:
        return None
    s = body.decode() if isinstance(body, bytes) else body
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        from urllib.parse import parse_qsl

        return sorted(parse_qsl(s))


def canon(method, host, path, query, body, auth) -> dict:
    """Canonical, language-agnostic request form for comparison."""
    return {
        "method": method,
        "host": host,
        "path": path,
        "query": sorted([list(x) for x in query]),
        "body": _parse_body(body),
        "auth": auth,
    }


def python_rows(binding, matrix, cred) -> dict[int, dict]:
    out = {}
    for i, (action, args) in enumerate(matrix):
        r = build_request(binding, action, args, cred)
        out[i] = canon(
            r.method,
            r.url.host,
            r.url.path,
            r.url.params.multi_items(),
            r.content or b"",
            r.headers.get("authorization"),
        )
    return out


TS_HARNESS = """\
import {{ buildRequest }} from "./src/runtime.ts";
import {{ {const} }} from "./src/{conn}.ts";
const M = {matrix};
const CRED = {cred};
M.forEach((row, i) => {{
  const r = buildRequest({const}, row[0], row[1], CRED);
  console.log(JSON.stringify({{ i, method: r.method, host: r.host, path: r.path,
    query: r.query, body: r.body, auth: r.auth }}));
}});
"""

GO_HARNESS = """\
package toolsconnector

import (
\t"encoding/json"
\t"os"
\t"testing"
)

func TestSDKParityGen(t *testing.T) {{
\tvar matrix [][2]any
\tjson.Unmarshal([]byte(os.Getenv("SDKP_MATRIX")), &matrix)
\tcred := os.Getenv("SDKP_CRED")
\tf, _ := os.Create(os.Getenv("SDKP_OUT"))
\tdefer f.Close()
\tenc := json.NewEncoder(f)
\tfor i, row := range matrix {{
\t\taction := row[0].(string)
\t\targs, _ := row[1].(map[string]any)
\t\tif args == nil {{ args = map[string]any{{}} }}
\t\tr := BuildRequest({const}, action, args, cred)
\t\tout := map[string]any{{"i": i, "method": r.Method, "host": r.Host,
\t\t\t"path": r.Path, "query": r.Query, "body": r.Body, "auth": r.Auth}}
\t\tenc.Encode(out)
\t}}
}}
"""


def ts_rows(conn, const, matrix, cred) -> dict[int, dict]:
    ts_dir = ROOT / "sdks" / "typescript"
    harness = ts_dir / ".sdkparity.ts"
    harness.write_text(
        TS_HARNESS.format(const=const, conn=conn, matrix=json.dumps(matrix), cred=json.dumps(cred))
    )
    try:
        p = subprocess.run(
            ["node", ".sdkparity.ts"], cwd=ts_dir, capture_output=True, text=True, timeout=120
        )
        if p.returncode != 0:
            raise RuntimeError(f"TS harness failed:\n{p.stderr}")
        out = {}
        for line in p.stdout.splitlines():
            if not line.strip().startswith("{"):
                continue
            d = json.loads(line)
            out[d["i"]] = canon(d["method"], d["host"], d["path"], d["query"], d["body"], d["auth"])
        return out
    finally:
        harness.unlink(missing_ok=True)


def go_rows(const, matrix, cred) -> dict[int, dict]:
    go_dir = ROOT / "sdks" / "go"
    harness = go_dir / "zz_sdkparity_gen_test.go"
    harness.write_text(GO_HARNESS.format(const=const))
    out_path = Path(tempfile.gettempdir()) / "sdkp_out.jsonl"
    env = {
        **os.environ,
        "SDKP_MATRIX": json.dumps(matrix),
        "SDKP_CRED": cred,
        "SDKP_OUT": str(out_path),
    }
    try:
        p = subprocess.run(
            ["go", "test", "-run", "TestSDKParityGen", "-count=1"],
            cwd=go_dir,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        if p.returncode != 0:
            raise RuntimeError(f"Go harness failed:\n{p.stdout}\n{p.stderr}")
        out = {}
        for line in out_path.read_text().splitlines():
            d = json.loads(line)
            q = d.get("query") or []
            out[d["i"]] = canon(d["method"], d["host"], d["path"], q, d["body"], d["auth"])
        return out
    finally:
        harness.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)


def main() -> int:
    conn = sys.argv[1] if len(sys.argv) > 1 else "notion"
    mod_name, const, matrix_mod, cred = CONNECTORS[conn]

    import importlib

    binding = getattr(importlib.import_module(mod_name), const)
    if matrix_mod == "spike":
        # Stripe/GitHub matrices live in the spike harness: MATRIX[conn] = (cred, [(action, args)]).
        cred, actions = importlib.import_module("experiments.sdk_spike.parity").MATRIX[conn]
        matrix = [[action, dict(args)] for action, args in actions]
    else:
        matrix = [
            [action, dict(args)] for action, args in importlib.import_module(matrix_mod).MATRIX
        ]

    py = python_rows(binding, matrix, cred)
    ts = ts_rows(conn, const, matrix, cred)
    go = go_rows(conn.upper(), matrix, cred)  # Go binding var is NOTION, not NOTION_BINDING

    print("\n" + "=" * 74)
    print(f"  CROSS-LANGUAGE SDK PARITY — {conn}   (Python · TypeScript · Go)")
    print("=" * 74)
    npass = 0
    for i, (action, _) in enumerate(matrix):
        p, t, g = py.get(i), ts.get(i), go.get(i)
        ok = p == t == g
        npass += ok
        badge = f"{GREEN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
        print(f"  {badge}  {conn}.{action}")
        if not ok:
            if t != p:
                print(f"        TS  != PY\n          py={p}\n          ts={t}")
            if g != p:
                print(f"        GO  != PY\n          py={p}\n          go={g}")
    print("-" * 74)
    print(f"  {npass}/{len(matrix)} identical across Python · TypeScript · Go")
    print("-" * 74 + "\n")
    return 0 if npass == len(matrix) else 1


if __name__ == "__main__":
    raise SystemExit(main())
