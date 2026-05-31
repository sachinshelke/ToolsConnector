// runtime.ts — ToolsConnector TS runtime (per-language core, hand-authored once).
// Erasable TypeScript: runs under `node runtime.ts` (type-strip) AND type-checks under tsc.
// Mirrors experiments/sdk_spike/executor.py exactly. No Node-only globals (uses fetch/URL/btoa).

export type Loc = "path" | "query" | "header" | "body";
export type Style = "simple" | "indexed" | "indexed_object" | "bracket" | "form_explode";
export type AuthKind = "bearer" | "header_key" | "basic_split";
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
