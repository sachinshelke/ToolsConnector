"""Production multi-language SDK generator — emits native TS + Go clients from the
*production* connector bindings (``src/toolsconnector/connectors/*/binding.py``).

This is the promoted, load-bearing successor to ``experiments/sdk_spike/gen_{ts,go}.py``:
it reads the same ``ConnectorBinding`` objects that drive the Python runtime
(``toolsconnector.spec.executor``) and re-emits them into the shipped packages:

  sdks/typescript/src/<connector>.ts   typed args + client class + the binding literal
  sdks/go/<connector>.go               typed arg structs + client + embedded binding

The per-language *runtimes* (runtime.ts / runtime.go) are hand-authored once and
already mirror ``executor.py``. Everything connector-specific is generated, so a
connector bound in Python flows to every language by re-running this.

Run:  .venv/bin/python scripts/gen_sdks.py notion
      .venv/bin/python scripts/gen_sdks.py            # all wired connectors
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from toolsconnector.connectors.github.binding import GITHUB_BINDING
from toolsconnector.connectors.notion.binding import NOTION_BINDING
from toolsconnector.connectors.slack.binding import SLACK_BINDING
from toolsconnector.connectors.stripe.binding import STRIPE_BINDING

ROOT = Path(__file__).resolve().parent.parent
TS_SRC = ROOT / "sdks" / "typescript" / "src"
GO_DIR = ROOT / "sdks" / "go"

# Production bindings, keyed by the name used for files + clients.
BINDINGS = {
    "stripe": STRIPE_BINDING,
    "github": GITHUB_BINDING,
    "notion": NOTION_BINDING,
    "slack": SLACK_BINDING,
}

_INITIALISMS = ("id", "url", "api", "sku", "uri", "ts")

# Abstract type -> TS type.
_TS_TY = {
    "string": "string",
    "number": "number",
    "boolean": "boolean",
    "string[]": "string[]",
    "object": "Record<string, unknown>",
    "object[]": "Array<Record<string, unknown>>",
    "smap": "Record<string, string>",
    "smap[]": "Array<Record<string, string>>",
}
# Abstract type -> (Go value type, is_scalar).
_GO_TY = {
    "string": ("string", True),
    "number": ("int", True),
    "boolean": ("bool", True),
    "string[]": ("[]string", False),
    "smap": ("map[string]string", False),
    "smap[]": ("[]map[string]string", False),
    "object": ("map[string]any", False),
    "object[]": ("[]map[string]any", False),
}


def camel(s: str) -> str:
    a = s.split("_")
    return a[0] + "".join(w[:1].upper() + w[1:] for w in a[1:])


def pascal(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in s.split("_"))


def go_pascal(s: str) -> str:
    return "".join(
        w.upper() if w in _INITIALISMS else (w[:1].upper() + w[1:]) for w in s.split("_")
    )


def infer_ty(p) -> str:
    """Abstract type for codegen — uses the binding's explicit ``ty`` when set."""
    if p.ty:
        return p.ty
    sv = p.style.value
    if sv in ("indexed", "bracket", "form_explode"):
        return "string[]"
    if sv == "indexed_object":
        return "smap[]"
    if sv == "map":
        return "smap"
    if isinstance(p.default, bool):  # before int — bool subclasses int
        return "boolean"
    if p.max is not None or isinstance(p.default, int):
        return "number"
    return "string"


def _typed_fields(a):
    """(py_name, abstract_ty, required) for every arg the typed client exposes.

    Includes the action's declared params PLUS a synthetic field for a
    ``raw_body_param`` (e.g. Notion update_block ``content``), which is consumed
    by the runtime but never appears in ``params``.
    """
    out = []
    for p in a.params:
        in_default = p.location.value == "path" and ("{" + p.wire + "}") in a.path
        out.append((p.name, infer_ty(p), in_default or p.required))
    if getattr(a, "raw_body_param", None):
        rb = a.raw_body_param
        if rb not in {p.name for p in a.params}:
            out.append((rb, "object", True))  # the whole-body payload, required
    return out


# ---------------------------------------------------------------------------
# binding -> TS object literal (camelCase keys)
# ---------------------------------------------------------------------------


def _ep_ts(ep) -> dict:
    d = {
        "id": ep.id,
        "baseUrl": ep.base_url,
        "encoding": ep.encoding,
        "authKind": ep.auth_kind.value,
        "authHeader": ep.auth_header,
    }
    if ep.auth_cred_ctx:
        d["authCredCtx"] = ep.auth_cred_ctx
    if ep.extra_headers:
        d["extraHeaders"] = ep.extra_headers
    return d


def _param_ts(p) -> dict:
    d = {"name": p.name, "wire": p.wire, "location": p.location.value}
    if p.style.value != "simple":
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
    if getattr(p, "wrap", None):
        d["wrap"] = p.wrap
    if getattr(p, "wrap_key", None):
        d["wrapKey"] = p.wrap_key
    if getattr(p, "min", None) is not None:
        d["min"] = p.min
    if p.max is not None:
        d["max"] = p.max
    if p.max_items is not None:
        d["maxItems"] = p.max_items
    return d


def _pg_ts(pg) -> dict:
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


def _action_ts(a) -> dict:
    d = {
        "name": a.name,
        "method": a.method,
        "endpoint": a.endpoint,
        "path": a.path,
        "params": [_param_ts(p) for p in a.params],
    }
    if a.path_variants:
        d["pathVariants"] = [
            {"whenPresent": pv.when_present, "path": pv.path} for pv in a.path_variants
        ]
    if getattr(a, "raw_body_param", None):
        d["rawBodyParam"] = a.raw_body_param
    if a.body_wrap:
        d["bodyWrap"] = a.body_wrap
    if a.body_encoding:
        d["bodyEncoding"] = a.body_encoding
    if a.unwrap:
        d["unwrap"] = a.unwrap
    if a.pagination and a.pagination.kind.value != "none":
        d["pagination"] = _pg_ts(a.pagination)
    return d


def _binding_literal_ts(c) -> dict:
    d = {
        "name": c.name,
        "endpoints": {k: _ep_ts(v) for k, v in c.endpoints.items()},
        "defaultEndpoint": c.default_endpoint,
        "actions": {k: _action_ts(v) for k, v in c.actions.items()},
    }
    if c.ctx_vars:
        d["ctxVars"] = [{"name": cv.name, "source": cv.source} for cv in c.ctx_vars]
    if getattr(c, "escape_hatches", None):
        d["escapeHatches"] = list(c.escape_hatches)
    return d


def emit_ts(c) -> str:
    const = f"{c.name.upper()}_BINDING"
    lit = json.dumps(_binding_literal_ts(c), indent=2)
    L = [  # noqa: N806 — terse line-buffer for the code emitter
        "// AUTO-GENERATED from the production connector binding. Do not edit by hand.",
        "// Regenerate: .venv/bin/python scripts/gen_sdks.py",
        'import { execute } from "./runtime.ts";',
        'import type { ConnectorB } from "./runtime.ts";',
        "",
        f"export const {const}: ConnectorB = {lit};",
        "",
    ]
    for a in c.actions.values():
        fields = [
            f"  {name}{'' if req else '?'}: {_TS_TY[ty]};" for name, ty, req in _typed_fields(a)
        ]
        L.append(f"export interface {pascal(a.name)}Args {{")
        if fields:
            L.append("\n".join(fields))
        L.append("}")
        L.append("")
    ov = "Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>>"
    L.append(f"export class {pascal(c.name)} {{")
    L.append("  credential: string;")
    L.append(f"  overrides: {ov};")
    L.append(
        f"  constructor(credential: string, opts?: {{ overrides?: {ov} }}) {{ "
        "this.credential = credential; this.overrides = opts?.overrides ?? {}; }"
    )
    for a in c.actions.values():
        L.append(f"  /** {a.method} {a.path} */")
        L.append(f"  async {camel(a.name)}(args: {pascal(a.name)}Args): Promise<unknown> {{")
        L.append(
            f'    return execute({const}, "{a.name}", '
            f"args as unknown as Record<string, unknown>, this.credential);"
        )
        L.append("  }")
    for name in getattr(c, "escape_hatches", []):
        L.append(
            f"  /** ESCAPE HATCH — provide via new {pascal(c.name)}(cred, {{ overrides }}). */"
        )
        L.append(f"  async {camel(name)}(args: Record<string, unknown>): Promise<unknown> {{")
        L.append(f'    const fn = this.overrides["{name}"];')
        L.append(
            f'    if (!fn) throw new Error("{c.name}.{name} is an escape-hatch action; '
            'pass an override");'
        )
        L.append("    return fn(this.credential, args);")
        L.append("  }")
    L.append("}")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# binding -> Go client (binding embedded as JSON via model_dump_json)
# ---------------------------------------------------------------------------


def emit_go(c, package: str = "toolsconnector") -> str:
    C = go_pascal(c.name)  # noqa: N806 — connector PascalName, used throughout the emitter
    js = c.model_dump_json()
    assert "`" not in js, f"binding {c.name} contains a backtick; raw literal unsafe"
    L = [  # noqa: N806 — terse line-buffer for the code emitter
        "// Code generated by scripts/gen_sdks.py from the production binding. DO NOT EDIT.",
        f"package {package}",
        "",
        "import (",
        '\t"fmt"',
        '\t"net/http"',
        ")",
        "",
        f"// {c.name.upper()} is the declarative binding driving every {C} request.",
        f"var {c.name.upper()} = MustParseBinding(`{js}`)",
        "",
        f"type {C}Override func(cred string, args map[string]any) (any, error)",
        "",
        f"// {C} is an in-process, bring-your-own-key client.",
        f"type {C} struct {{",
        "\tcred      string",
        "\thttp      *http.Client",
        f"\toverrides map[string]{C}Override",
        "}",
        "",
        f"type {C}Option func(*{C})",
        "",
        f"func {C}WithHTTPClient(c *http.Client) {C}Option {{ return func(s *{C}) {{ s.http = c }} }}",
        "",
        f"func {C}WithOverride(action string, fn {C}Override) {C}Option {{",
        f"\treturn func(s *{C}) {{ s.overrides[action] = fn }}",
        "}",
        "",
        f"// New{C} constructs a client for the given API key.",
        f"func New{C}(credential string, opts ...{C}Option) *{C} {{",
        f"\ts := &{C}{{cred: credential, http: http.DefaultClient, "
        f"overrides: map[string]{C}Override{{}}}}",
        "\tfor _, o := range opts {",
        "\t\to(s)",
        "\t}",
        "\treturn s",
        "}",
        "",
        f"func (s *{C}) execute(action string, args map[string]any) (any, error) {{",
        f"\treturn ExecuteWith(s.http, {c.name.upper()}, action, args, s.cred)",
        "}",
        "",
        f"func (s *{C}) paginate(action string, args map[string]any) ([]any, error) {{",
        f"\treturn PaginateWith(s.http, {c.name.upper()}, action, args, s.cred)",
        "}",
        "",
    ]
    for a in c.actions.values():
        # Go has a flat package namespace, so arg-struct types are prefixed with
        # the connector (NotionListCommentsArgs) to avoid cross-connector clashes
        # (e.g. notion + github both expose list_comments). Methods live on the
        # receiver type, so they don't collide.
        args_ty = f"{C}{go_pascal(a.name)}Args"
        L.append(f"// {args_ty} are the arguments for {C}.{go_pascal(a.name)}.")
        L.append(f"type {args_ty} struct {{")
        field_lines, set_lines = [], []
        for name, ty, required in _typed_fields(a):
            goty, scalar = _GO_TY[ty]
            field = go_pascal(name)
            if required:
                field_lines.append(f"\t{field} {goty}")
                set_lines.append(f'\tm["{name}"] = a.{field}')
            elif scalar:
                field_lines.append(f"\t{field} *{goty}")
                set_lines.append(f'\tif a.{field} != nil {{ m["{name}"] = *a.{field} }}')
            else:
                field_lines.append(f"\t{field} {goty}")
                set_lines.append(f'\tif a.{field} != nil {{ m["{name}"] = a.{field} }}')
        L.extend(field_lines)
        L.append("}")
        L.append("")
        L.append(f"func (a {args_ty}) toMap() map[string]any {{")
        L.append("\tm := map[string]any{}")
        L.extend(set_lines)
        L.append("\treturn m")
        L.append("}")
        L.append("")
        L.append(f"// {go_pascal(a.name)} — {a.method} {a.path}")
        L.append(f"func (s *{C}) {go_pascal(a.name)}(args {args_ty}) (any, error) {{")
        L.append(f'\treturn s.execute("{a.name}", args.toMap())')
        L.append("}")
        L.append("")
        if a.pagination.kind.value != "none":
            L.append(f"// {go_pascal(a.name)}All walks every page of {a.name}.")
            L.append(f"func (s *{C}) {go_pascal(a.name)}All(args {args_ty}) ([]any, error) {{")
            L.append(f'\treturn s.paginate("{a.name}", args.toMap())')
            L.append("}")
            L.append("")
    for name in getattr(c, "escape_hatches", []):
        m = go_pascal(name)
        L.append(f'// {m} is an ESCAPE-HATCH: register an impl with {C}WithOverride("{name}", fn).')
        L.append(f"func (s *{C}) {m}(args map[string]any) (any, error) {{")
        L.append(f'\tfn, ok := s.overrides["{name}"]')
        L.append("\tif !ok {")
        L.append(
            f'\t\treturn nil, fmt.Errorf("{c.name}.{name} is an escape-hatch action; '
            'register an override")'
        )
        L.append("\t}")
        L.append("\treturn fn(s.cred, args)")
        L.append("}")
        L.append("")
    return "\n".join(L)


def _update_ts_index(names: list[str]) -> None:
    """Ensure index.ts re-exports each generated connector's client + binding."""
    idx = TS_SRC / "index.ts"
    text = idx.read_text()
    for n in names:
        cls = pascal(n)
        line = f'export {{ {cls}, {n.upper()}_BINDING }} from "./{n}.ts";'
        if line not in text:
            # insert after the last connector export line
            text = text.rstrip() + "\n" + line + "\n"
    idx.write_text(text)


def main() -> int:
    targets = sys.argv[1:] or list(BINDINGS)
    written = []
    for n in targets:
        c = BINDINGS[n]
        (TS_SRC / f"{n}.ts").write_text(emit_ts(c))
        (GO_DIR / f"{n}.go").write_text(emit_go(c))
        written += [f"sdks/typescript/src/{n}.ts", f"sdks/go/{n}.go"]
    _update_ts_index(targets)
    if gofmt := shutil.which("gofmt"):
        subprocess.run([gofmt, "-w", *(str(GO_DIR / f"{n}.go") for n in targets)], check=True)
    print(f"Generated {len(targets)} connector(s): {', '.join(targets)}")
    for w in written:
        print(f"    {w}")
    print("    sdks/typescript/src/index.ts (exports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
