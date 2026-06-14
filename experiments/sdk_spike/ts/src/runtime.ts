// runtime.ts — ToolsConnector TS runtime (per-language core, hand-authored once).
// Erasable TypeScript: runs under `node runtime.ts` (type-strip) AND type-checks under tsc.
// Mirrors experiments/sdk_spike/executor.py exactly. No Node-only globals (uses fetch/URL/btoa).

export type Loc = "path" | "query" | "header" | "body";
export type Style = "simple" | "indexed" | "indexed_object" | "bracket" | "form_explode" | "map";
export type AuthKind = "bearer" | "header_key" | "basic_split" | "basic_user";
export type PgKind = "offset_token" | "link_header" | "follow_url" | "last_id";

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
export interface ActionB {
  name: string; method: string; endpoint: string; path: string; params: ParamB[];
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
