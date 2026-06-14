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
from .parity import MATRIX, PAGI
from .specs import ALL

OUT = Path(__file__).resolve().parent / "ts"
SRC = OUT / "src"

TY = {
    "string": "string", "number": "number", "string[]": "string[]",
    "object": "Record<string, unknown>", "object[]": "Array<Record<string, unknown>>",
    "smap": "Record<string, string>", "smap[]": "Array<Record<string, string>>",
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
    if p.style == Style.MAP:
        return "smap"
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
    if getattr(pg, "id_field", "id") != "id":
        d["idField"] = pg.id_field
    if getattr(pg, "has_more_field", "has_more") != "has_more":
        d["hasMoreField"] = pg.has_more_field
    if pg.carry is not None:
        d["carry"] = pg.carry
    return d


def _action(a) -> dict:
    d = {"name": a.name, "method": a.method, "endpoint": a.endpoint, "path": a.path,
         "params": [_param(p) for p in a.params]}
    if a.path_variants:
        d["pathVariants"] = [{"whenPresent": pv.when_present, "path": pv.path} for pv in a.path_variants]
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
    if getattr(c, "escape_hatches", None):
        d["escapeHatches"] = list(c.escape_hatches)
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
    ov_type = "Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>>"
    lines.append(f"export class {pascal(c.name)} {{")
    lines.append("  credential: string;")
    lines.append(f"  overrides: {ov_type};")
    lines.append(
        f"  constructor(credential: string, opts?: {{ overrides?: {ov_type} }}) {{ "
        "this.credential = credential; this.overrides = opts?.overrides ?? {}; }"
    )
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
    # Escape-hatch actions: present in the typed surface, delegated to a
    # per-language hand-written override (the honest <2.7%).
    for name in getattr(c, "escape_hatches", []):
        lines.append(f"  /** ESCAPE HATCH — provide via new {pascal(c.name)}(cred, {{ overrides }}). */")
        lines.append(f"  async {camel(name)}(args: Record<string, unknown>): Promise<unknown> {{")
        lines.append(f'    const fn = this.overrides["{name}"];')
        lines.append(
            f'    if (!fn) throw new Error("{c.name}.{name} is an escape-hatch action; '
            f'pass an override");'
        )
        lines.append("    return fn(this.credential, args);")
        lines.append("  }")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def emit_parity() -> str:
    flat = []
    for cname, (cred, actions) in MATRIX.items():
        for action, kwargs in actions:
            flat.append({"connector": cname, "cred": cred, "action": action, "args": kwargs})
    pagi = [
        {"connector": c, "cred": cr, "action": a, "args": fa, "body": bd, "headers": hd}
        for (c, cr, a, fa, bd, hd) in PAGI
    ]
    consts = {c.name: f"{c.name.upper()}_BINDING" for c in ALL.values()}
    imports = "\n".join(
        f'import {{ {consts[n]} }} from "./{n}.ts";' for n in consts
    )
    bmap = ", ".join(f"{n}: {consts[n]}" for n in consts)
    return f"""// AUTO-GENERATED parity harness. Builds requests via the TS runtime and prints JSONL.
import {{ buildRequest, nextRequest }} from "./runtime.ts";
import type {{ BuiltRequest, ConnectorB }} from "./runtime.ts";
{imports}

const B: Record<string, ConnectorB> = {{ {bmap} }};
const MATRIX = {json.dumps(flat, indent=2)};
const PAGI = {json.dumps(pagi, indent=2)};

function emit(kind: string, connector: string, action: string, r: BuiltRequest | null) {{
  if (!r) {{ console.log(JSON.stringify({{ kind, connector, action, none: true }})); return; }}
  console.log(JSON.stringify({{
    kind, connector, action, method: r.method, host: r.host, path: r.path,
    query: r.query, body: r.body, contentType: r.contentType, auth: r.auth,
  }}));
}}

for (const m of MATRIX) {{
  emit("first", m.connector, m.action,
       buildRequest(B[m.connector], m.action, m.args as Record<string, unknown>, m.cred));
}}
for (const m of PAGI) {{
  emit("next", m.connector, m.action, nextRequest(
    B[m.connector], m.action, m.args as Record<string, unknown>, m.cred,
    m.body as Record<string, unknown>, m.headers as Record<string, string>));
}}
"""


RUNTIME_TS = r'''// runtime.ts — ToolsConnector TS runtime (per-language core, hand-authored once).
// Erasable TypeScript: runs under `node runtime.ts` (type-strip) AND type-checks under tsc.
// Mirrors experiments/sdk_spike/executor.py exactly. No Node-only globals (uses fetch/URL/btoa).

export type Loc = "path" | "query" | "header" | "body";
export type Style = "simple" | "indexed" | "indexed_object" | "bracket" | "form_explode" | "map";
export type AuthKind = "bearer" | "header_key" | "basic_split" | "basic_user";
export type PgKind = "offset_token" | "link_header" | "link_follow" | "follow_url" | "last_id";

export interface ParamB {
  name: string; wire: string; location: Loc; style?: Style; required?: boolean;
  default?: unknown; subkeys?: string[]; subkeyDefaults?: Record<string, unknown>;
  bodyKey?: string; itemWrap?: string; max?: number; maxItems?: number;
}
export interface PgB {
  kind: PgKind; itemsField?: string; tokenField?: string;
  tokenParamPy?: string; linkRel?: string; idField?: string; hasMoreField?: string;
  carry?: string[];
}
export interface EndpointB {
  id: string; baseUrl: string; encoding: "json" | "form"; authKind: AuthKind;
  authHeader: string; authCredCtx?: string; extraHeaders?: Record<string, string>;
}
export interface PathVariantB { whenPresent: string; path: string; }
export interface ActionB {
  name: string; method: string; endpoint: string; path: string; params: ParamB[];
  pathVariants?: PathVariantB[];
  bodyWrap?: string; bodyEncoding?: "json" | "form"; unwrap?: string; pagination?: PgB;
}
export interface CtxVar { name: string; source: string; }
export interface ConnectorB {
  name: string; endpoints: Record<string, EndpointB>; defaultEndpoint: string;
  ctxVars?: CtxVar[]; actions: Record<string, ActionB>; escapeHatches?: string[];
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

// Serialize ONE present param value into wire (key, value) pairs by style.
// Shared by query strings and form bodies — Stripe puts list/object params
// (payment_method_types[i], line_items[i][price]) in the BODY, so both paths
// need the same finite style vocabulary. Mirrors executor.py::_styled_pairs.
function styledPairs(p: ParamB, v: unknown): [string, string][] {
  const style = p.style ?? "simple";
  if (style === "indexed") {
    const seq = p.maxItems ? (v as unknown[]).slice(0, p.maxItems) : (v as unknown[]);
    return seq.map((it, i) => [`${p.wire}[${i}]`, String(it)] as [string, string]);
  }
  if (style === "indexed_object") {
    const out: [string, string][] = [];
    (v as Record<string, unknown>[]).forEach((it, i) => {
      for (const sk of p.subkeys ?? [])
        out.push([`${p.wire}[${i}][${sk}]`, String(it[sk] ?? (p.subkeyDefaults ?? {})[sk])]);
    });
    return out;
  }
  if (style === "bracket") {
    const seq = p.maxItems ? (v as unknown[]).slice(0, p.maxItems) : (v as unknown[]);
    return seq.map((it) => [`${p.wire}[]`, String(it)] as [string, string]);
  }
  if (style === "form_explode")
    return (v as unknown[]).map((it) => [p.wire, String(it)] as [string, string]);
  if (style === "map")
    return Object.entries(v as Record<string, unknown>).map(
      ([k, val]) => [`${p.wire}[${k}]`, String(val)] as [string, string]);
  return [[p.wire, String(clamp(v, p.max))]];  // simple
}

function queryPairs(action: ActionB, args: Record<string, unknown>): [string, string][] {
  const out: [string, string][] = [];
  for (const p of action.params) {
    if (p.location !== "query") continue;
    const v = args[p.name] ?? p.default;
    if (present(v)) out.push(...styledPairs(p, v));
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
      if (present(v)) pairs.push(...styledPairs(p, v));
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
  // conditional path: first variant whose arg is truthy wins, else default path
  let chosenPath = action.path;
  for (const pv of action.pathVariants ?? [])
    if (args[pv.whenPresent]) { chosenPath = pv.path; break; }
  const base = fmt(ep.baseUrl, ctx);
  const path = fmt(chosenPath, ctx, pathExtra);
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

// ---- Pagination: compute the next-page request (mirrors executor.py::next_request) ----
const LINK_RE = /<([^>]+)>;\s*rel="?(\w+)"?/g;
const PAGE_INFO_RE = /[?&]page_info=([^&>]+)/;

function parseLinkNext(linkHeader: string | undefined, rel: string): string | null {
  if (!linkHeader) return null;
  for (const m of linkHeader.matchAll(LINK_RE)) {
    if (m[2] === rel) { const pm = PAGE_INFO_RE.exec(m[1]); if (pm) return pm[1]; }
  }
  return null;
}

function parseLinkRel(linkHeader: string | undefined, rel: string): string | null {
  if (!linkHeader) return null;
  for (const m of linkHeader.matchAll(LINK_RE)) if (m[2] === rel) return m[1];
  return null;
}

export function nextRequest(
  conn: ConnectorB, actionName: string, prevArgs: Record<string, unknown>, credential: string,
  body?: Record<string, unknown>, headers?: Record<string, string>,
): BuiltRequest | null {
  const action = conn.actions[actionName];
  const ep = conn.endpoints[action.endpoint];
  const pg = action.pagination;
  if (!pg) return null;
  const b = body ?? {}; const h = headers ?? {};
  const carried = (): Record<string, unknown> =>
    pg.carry == null
      ? { ...prevArgs }
      : Object.fromEntries(pg.carry.filter((k) => k in prevArgs).map((k) => [k, prevArgs[k]]));

  if (pg.kind === "follow_url") {
    const uri = pg.tokenField ? b[pg.tokenField] : null;
    if (!uri) return null;
    const ctx = deriveCtx(conn, credential);
    const url = new URL(String(uri), fmt(ep.baseUrl, ctx)).toString();
    const hh: Record<string, string> = { ...(ep.extraHeaders ?? {}) };
    const authCred = ep.authCredCtx ? ctx[ep.authCredCtx] ?? "" : credential;
    const auth = applyAuth(hh, ep, authCred);
    const u = new URL(url);
    return {
      method: "GET", url, scheme: u.protocol.replace(":", ""), host: u.host, path: u.pathname,
      query: [...u.searchParams.entries()] as [string, string][], body: null, contentType: null,
      headers: hh, auth,
    };
  }
  if (pg.kind === "offset_token") {
    const cursor = pg.tokenField ? b[pg.tokenField] : null;
    if (cursor == null) return null;
    const n = carried(); n[pg.tokenParamPy as string] = cursor;
    return buildRequest(conn, actionName, n, credential);
  }
  if (pg.kind === "last_id") {
    const items = (pg.itemsField ? b[pg.itemsField] : []) as Record<string, unknown>[];
    if (!b[pg.hasMoreField ?? "has_more"] || !items || items.length === 0) return null;
    const cursor = items[items.length - 1][pg.idField ?? "id"];
    if (cursor == null) return null;
    const n = carried(); n[pg.tokenParamPy as string] = cursor;
    return buildRequest(conn, actionName, n, credential);
  }
  if (pg.kind === "link_header") {
    const cursor = parseLinkNext(h["link"], pg.linkRel ?? "next");
    if (!cursor) return null;
    const n = carried(); n[pg.tokenParamPy as string] = cursor;
    return buildRequest(conn, actionName, n, credential);
  }
  if (pg.kind === "link_follow") {
    // GitHub: the Link rel=next URL is absolute & carries every query param; GET it.
    const nextUrl = parseLinkRel(h["link"], pg.linkRel ?? "next");
    if (!nextUrl) return null;
    const ctx = deriveCtx(conn, credential);
    const hh: Record<string, string> = { ...(ep.extraHeaders ?? {}) };
    const authCred = ep.authCredCtx ? ctx[ep.authCredCtx] ?? "" : credential;
    const auth = applyAuth(hh, ep, authCred);
    const u = new URL(nextUrl);
    return {
      method: "GET", url: nextUrl, scheme: u.protocol.replace(":", ""), host: u.host, path: u.pathname,
      query: [...u.searchParams.entries()] as [string, string][], body: null, contentType: null,
      headers: hh, auth,
    };
  }
  return null;
}

// Async paginator: walks every page, yielding each item. The usable surface
// on top of nextRequest — `for await (const it of paginate(...)) {}`.
export async function* paginate(
  conn: ConnectorB, actionName: string, args: Record<string, unknown>, credential: string,
): AsyncGenerator<unknown> {
  const a = conn.actions[actionName];
  let req: BuiltRequest | null = buildRequest(conn, actionName, args, credential);
  while (req) {
    const qs = req.query.length
      ? "?" + req.query.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&")
      : "";
    const resp = await fetch(req.url + qs, { method: req.method, headers: req.headers, body: req.body ?? undefined });
    const data = (await resp.json()) as Record<string, unknown>;
    const items = (a.unwrap ? data[a.unwrap] : data) as unknown[];
    for (const it of items ?? []) yield it;
    req = nextRequest(conn, actionName, args, credential, data,
                      Object.fromEntries(resp.headers.entries()));
  }
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
