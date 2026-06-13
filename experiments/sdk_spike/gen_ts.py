"""TypeScript generator — emits a native, in-process TS SDK from the bindings.

Reads the SAME ConnectorBinding specs the Python runtime uses and emits:
  ts/src/runtime.ts        the per-language core (hand-authored once; ports executor.py)
  ts/src/<connector>.ts    generated: typed args interfaces + a client class + the binding
  ts/src/parity.ts         runnable harness that builds requests via the TS runtime
  ts/tsconfig.json         strict, lib ES2022+DOM (no @types/node needed)
  ts/package.json          ESM

Run:  .venv/bin/python -m experiments.sdk_spike.gen_ts
Then: node experiments/sdk_spike/ts/src/parity.ts      (Node 23 type-strips & runs)
      .venv/bin/python -m experiments.sdk_spike.ts_parity   (cross-language parity vs Python)
"""

from __future__ import annotations

import json
from pathlib import Path

from .binding_ir import Style
from .parity import MATRIX
from .specs import ALL

OUT = Path(__file__).resolve().parent / "ts"
SRC = OUT / "src"

TY = {
    "string": "string", "number": "number", "string[]": "string[]",
    "object": "Record<string, unknown>", "object[]": "Array<Record<string, unknown>>",
    "smap[]": "Array<Record<string, string>>",
}


def camel(s: str) -> str:
    a = s.split("_")
    return a[0] + "".join(w[:1].upper() + w[1:] for w in a[1:])


def pascal(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in s.split("_"))


def infer_ty(p) -> str:
    if p.ty:
        return p.ty
    if p.style in (Style.INDEXED, Style.BRACKET, Style.FORM_EXPLODE):
        return "string[]"
    if p.style == Style.INDEXED_OBJECT:
        return "smap[]"
    if p.max is not None or isinstance(p.default, int):
        return "number"
    return "string"


# --- binding -> TS object literal (camelCase keys; value-maps kept opaque) ---

def _ep(ep) -> dict:
    d = {"id": ep.id, "baseUrl": ep.base_url, "encoding": ep.encoding,
         "authKind": ep.auth_kind.value, "authHeader": ep.auth_header}
    if ep.auth_cred_ctx:
        d["authCredCtx"] = ep.auth_cred_ctx
    if ep.extra_headers:
        d["extraHeaders"] = ep.extra_headers
    return d


def _param(p) -> dict:
    d = {"name": p.name, "wire": p.wire, "location": p.location.value}
    if p.style != Style.SIMPLE:
        d["style"] = p.style.value
    if p.required:
        d["required"] = True
    if p.default is not None:
        d["default"] = p.default
    if p.subkeys:
        d["subkeys"] = p.subkeys
    if p.subkey_defaults:
        d["subkeyDefaults"] = p.subkey_defaults
    if p.body_key:
        d["bodyKey"] = p.body_key
    if p.item_wrap:
        d["itemWrap"] = p.item_wrap
    if p.max is not None:
        d["max"] = p.max
    if p.max_items is not None:
        d["maxItems"] = p.max_items
    return d


def _pg(pg) -> dict:
    d = {"kind": pg.kind.value}
    if pg.items_field:
        d["itemsField"] = pg.items_field
    if pg.token_field:
        d["tokenField"] = pg.token_field
    if pg.token_param_py:
        d["tokenParamPy"] = pg.token_param_py
    if pg.link_rel != "next":
        d["linkRel"] = pg.link_rel
    if pg.carry is not None:
        d["carry"] = pg.carry
    return d


def _action(a) -> dict:
    d = {"name": a.name, "method": a.method, "endpoint": a.endpoint, "path": a.path,
         "params": [_param(p) for p in a.params]}
    if a.body_wrap:
        d["bodyWrap"] = a.body_wrap
    if a.body_encoding:
        d["bodyEncoding"] = a.body_encoding
    if a.unwrap:
        d["unwrap"] = a.unwrap
    if a.pagination and a.pagination.kind.value != "none":
        d["pagination"] = _pg(a.pagination)
    return d


def binding_literal(c) -> dict:
    d = {"name": c.name,
         "endpoints": {k: _ep(v) for k, v in c.endpoints.items()},
         "defaultEndpoint": c.default_endpoint,
         "actions": {k: _action(v) for k, v in c.actions.items()}}
    if c.ctx_vars:
        d["ctxVars"] = [{"name": cv.name, "source": cv.source} for cv in c.ctx_vars]
    return d


def emit_connector(c) -> str:
    const = f"{c.name.upper()}_BINDING"
    lit = json.dumps(binding_literal(c), indent=2)
    lines = [
        "// AUTO-GENERATED from the connector binding. Do not edit by hand.",
        'import { execute } from "./runtime.ts";',
        'import type { ConnectorB } from "./runtime.ts";',
        "",
        f"export const {const}: ConnectorB = {lit};",
        "",
    ]
    # args interfaces
    for a in c.actions.values():
        fields = []
        for p in a.params:
            req = p.location.value == "path" or p.required
            fields.append(f"  {p.name}{'' if req else '?'}: {TY[infer_ty(p)]};")
        body = "\n".join(fields) if fields else ""
        lines.append(f"export interface {pascal(a.name)}Args {{")
        if body:
            lines.append(body)
        lines.append("}")
        lines.append("")
    # client class
    lines.append(f"export class {pascal(c.name)} {{")
    lines.append("  credential: string;")
    lines.append("  constructor(credential: string) { this.credential = credential; }")
    for a in c.actions.values():
        lines.append(f"  /** {a.method} {a.path} */")
        lines.append(
            f"  async {camel(a.name)}(args: {pascal(a.name)}Args): Promise<unknown> {{"
        )
        lines.append(
            f'    return execute({const}, "{a.name}", '
            f"args as unknown as Record<string, unknown>, this.credential);"
        )
        lines.append("  }")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def emit_parity() -> str:
    flat = []
    for cname, (cred, actions) in MATRIX.items():
        for action, kwargs in actions:
            flat.append({"connector": cname, "cred": cred, "action": action, "args": kwargs})
    consts = {c.name: f"{c.name.upper()}_BINDING" for c in ALL.values()}
    imports = "\n".join(
        f'import {{ {consts[n]} }} from "./{n}.ts";' for n in consts
    )
    bmap = ", ".join(f"{n}: {consts[n]}" for n in consts)
    return f"""// AUTO-GENERATED parity harness. Builds requests via the TS runtime and prints JSONL.
import {{ buildRequest }} from "./runtime.ts";
import type {{ ConnectorB }} from "./runtime.ts";
{imports}

const B: Record<string, ConnectorB> = {{ {bmap} }};
const MATRIX = {json.dumps(flat, indent=2)};

for (const m of MATRIX) {{
  const r = buildRequest(B[m.connector], m.action, m.args as Record<string, unknown>, m.cred);
  console.log(JSON.stringify({{
    connector: m.connector, action: m.action, method: r.method,
    host: r.host, path: r.path, query: r.query, body: r.body,
    contentType: r.contentType, auth: r.auth,
  }}));
}}
"""


RUNTIME_TS = r'''// runtime.ts — ToolsConnector TS runtime (per-language core, hand-authored once).
// Erasable TypeScript: runs under `node runtime.ts` (type-strip) AND type-checks under tsc.
// Mirrors experiments/sdk_spike/executor.py exactly. No Node-only globals (uses fetch/URL/btoa).

export type Loc = "path" | "query" | "header" | "body";
export type Style = "simple" | "indexed" | "indexed_object" | "bracket" | "form_explode";
export type AuthKind = "bearer" | "header_key" | "basic_split" | "basic_user";
export type PgKind = "offset_token" | "link_header" | "follow_url";

export interface ParamB {
  name: string; wire: string; location: Loc; style?: Style; required?: boolean;
  default?: unknown; subkeys?: string[]; subkeyDefaults?: Record<string, unknown>;
  bodyKey?: string; itemWrap?: string; max?: number; maxItems?: number;
}
export interface PgB {
  kind: PgKind; itemsField?: string; tokenField?: string;
  tokenParamPy?: string; linkRel?: string; carry?: string[];
}
export interface EndpointB {
  id: string; baseUrl: string; encoding: "json" | "form"; authKind: AuthKind;
  authHeader: string; authCredCtx?: string; extraHeaders?: Record<string, string>;
}
export interface ActionB {
  name: string; method: string; endpoint: string; path: string; params: ParamB[];
  bodyWrap?: string; bodyEncoding?: "json" | "form"; unwrap?: string; pagination?: PgB;
}
export interface CtxVar { name: string; source: string; }
export interface ConnectorB {
  name: string; endpoints: Record<string, EndpointB>; defaultEndpoint: string;
  ctxVars?: CtxVar[]; actions: Record<string, ActionB>;
}
export interface BuiltRequest {
  method: string; url: string; scheme: string; host: string; path: string;
  query: [string, string][]; body: string | null; contentType: string | null;
  headers: Record<string, string>; auth: string | null;
}

function splitN(s: string, sep: string, n: number): string[] {
  const parts = s.split(sep);
  if (parts.length <= n) return parts;
  return [...parts.slice(0, n), parts.slice(n).join(sep)];
}

function deriveCtx(conn: ConnectorB, cred: string): Record<string, string> {
  const ctx: Record<string, string> = {};
  for (const cv of conn.ctxVars ?? []) {
    if (cv.source === "whole") ctx[cv.name] = cred;
    else if (cv.source.startsWith("split:")) {
      const [, idx, sep] = splitN(cv.source, ":", 2);
      ctx[cv.name] = cred.split(sep)[Number(idx)] ?? "";
    }
  }
  return ctx;
}

function present(v: unknown): boolean { return v !== undefined && v !== null; }
function clamp(v: unknown, mx?: number): unknown {
  return mx !== undefined && typeof v === "number" ? Math.min(v, mx) : v;
}
function fmt(s: string, ctx: Record<string, string>, extra: Record<string, unknown> = {}): string {
  return s.replace(/\{(\w+)\}/g, (_m, k) => String(extra[k] ?? ctx[k] ?? `{${k}}`));
}

function queryPairs(action: ActionB, args: Record<string, unknown>): [string, string][] {
  const out: [string, string][] = [];
  for (const p of action.params) {
    if (p.location !== "query") continue;
    const v = args[p.name] ?? p.default;
    if (!present(v)) continue;
    const style = p.style ?? "simple";
    if (style === "simple") out.push([p.wire, String(clamp(v, p.max))]);
    else if (style === "indexed")
      (v as unknown[]).forEach((it, i) => out.push([`${p.wire}[${i}]`, String(it)]));
    else if (style === "indexed_object")
      (v as Record<string, unknown>[]).forEach((it, i) => {
        for (const sk of p.subkeys ?? [])
          out.push([`${p.wire}[${i}][${sk}]`, String(it[sk] ?? (p.subkeyDefaults ?? {})[sk])]);
      });
    else if (style === "bracket") {
      const seq = p.maxItems ? (v as unknown[]).slice(0, p.maxItems) : (v as unknown[]);
      for (const it of seq) out.push([`${p.wire}[]`, String(it)]);
    } else if (style === "form_explode")
      for (const it of v as unknown[]) out.push([p.wire, String(it)]);
  }
  return out;
}

function buildBody(
  action: ActionB, encoding: string, args: Record<string, unknown>,
): [string | null, string | null] {
  const bodyParams = action.params.filter((p) => p.location === "body");
  if (bodyParams.length === 0) return [null, null];
  if (encoding === "form") {
    const pairs: [string, string][] = [];
    for (const p of bodyParams) {
      const v = args[p.name] ?? p.default;
      if (present(v)) pairs.push([p.wire, String(v)]);
    }
    return [
      pairs.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&"),
      "application/x-www-form-urlencoded",
    ];
  }
  let obj: Record<string, unknown> = {};
  for (const p of bodyParams) {
    let v = args[p.name] ?? p.default;
    if (!present(v)) continue;
    if (p.itemWrap) {
      const seq = p.maxItems ? (v as unknown[]).slice(0, p.maxItems) : (v as unknown[]);
      v = seq.map((e) => ({ [p.itemWrap as string]: e }));
    }
    obj[p.bodyKey ?? p.wire] = v;
  }
  if (action.bodyWrap) obj = { [action.bodyWrap]: obj };
  return [JSON.stringify(obj), "application/json"];
}

function applyAuth(headers: Record<string, string>, ep: EndpointB, cred: string): string | null {
  if (ep.authKind === "bearer") { headers[ep.authHeader] = `Bearer ${cred}`; return headers[ep.authHeader]; }
  if (ep.authKind === "header_key") { headers[ep.authHeader] = cred; return cred; }
  if (ep.authKind === "basic_split") { headers[ep.authHeader] = `Basic ${btoa(cred)}`; return headers[ep.authHeader]; }
  if (ep.authKind === "basic_user") { headers[ep.authHeader] = `Basic ${btoa(cred + ":")}`; return headers[ep.authHeader]; }
  return null;
}

export function buildRequest(
  conn: ConnectorB, actionName: string, args: Record<string, unknown>, credential: string,
): BuiltRequest {
  const action = conn.actions[actionName];
  const ep = conn.endpoints[action.endpoint];
  const ctx = deriveCtx(conn, credential);

  const pathExtra: Record<string, unknown> = {};
  for (const p of action.params)
    if (p.location === "path") pathExtra[p.wire] = args[p.name] ?? p.default;
  const base = fmt(ep.baseUrl, ctx);
  const path = fmt(action.path, ctx, pathExtra);
  const urlStr = base.replace(/\/+$/, "") + "/" + path.replace(/^\/+/, "");

  const query = queryPairs(action, args);
  const encoding = action.bodyEncoding ?? ep.encoding;
  const [body, contentType] = buildBody(action, encoding, args);

  const headers: Record<string, string> = { ...(ep.extraHeaders ?? {}) };
  for (const p of action.params)
    if (p.location === "header") {
      const v = args[p.name] ?? p.default;
      if (present(v)) headers[p.wire] = String(v);
    }
  const authCred = ep.authCredCtx ? ctx[ep.authCredCtx] ?? "" : credential;
  const auth = applyAuth(headers, ep, authCred);
  if (contentType) headers["content-type"] = contentType;

  const u = new URL(urlStr);
  return {
    method: action.method, url: urlStr, scheme: u.protocol.replace(":", ""),
    host: u.host, path: u.pathname, query, body, contentType, headers, auth,
  };
}

export async function execute(
  conn: ConnectorB, actionName: string, args: Record<string, unknown>, credential: string,
): Promise<unknown> {
  const r = buildRequest(conn, actionName, args, credential);
  const qs = r.query.length
    ? "?" + r.query.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&")
    : "";
  const resp = await fetch(r.url + qs, {
    method: r.method, headers: r.headers, body: r.body ?? undefined,
  });
  const data = (await resp.json()) as Record<string, unknown>;
  const a = conn.actions[actionName];
  return a.unwrap ? data[a.unwrap] : data;
}
'''

TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2022", "DOM"],
    "strict": true,
    "allowImportingTsExtensions": true,
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
"""

PACKAGE = """{
  "name": "@toolsconnector/sdk-ts-spike",
  "private": true,
  "type": "module",
  "description": "Generated TS SDK (de-risking spike) — do not publish."
}
"""


def main() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    (SRC / "runtime.ts").write_text(RUNTIME_TS)
    written = ["src/runtime.ts"]
    for c in ALL.values():
        (SRC / f"{c.name}.ts").write_text(emit_connector(c))
        written.append(f"src/{c.name}.ts")
    (SRC / "parity.ts").write_text(emit_parity())
    (OUT / "tsconfig.json").write_text(TSCONFIG)
    (OUT / "package.json").write_text(PACKAGE)
    written += ["src/parity.ts", "tsconfig.json", "package.json"]

    n_actions = sum(len(c.actions) for c in ALL.values())
    print(f"Generated TS SDK → {OUT}")
    print(f"  connectors: {len(ALL)}  |  typed methods: {n_actions}  |  files: {len(written)}")
    for w in written:
        print(f"    ts/{w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
