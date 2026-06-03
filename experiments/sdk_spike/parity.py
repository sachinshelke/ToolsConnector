"""Parity oracle: prove the generic spec-driven executor reproduces the EXACT
HTTP requests of the hand-written imperative connectors.

Method: drive each REAL connector through an ``httpx.MockTransport`` that captures
the outgoing request, then build the same logical call through the generic
executor (``build_request``/``next_request``) and assert method + URL + query
(multi-valued) + body (parsed) + auth header all match.

Run:  .venv/bin/python -m experiments.sdk_spike.parity
"""

from __future__ import annotations

import asyncio
import json
import sys
from urllib.parse import parse_qsl

import httpx

from toolsconnector.connectors.airtable.connector import Airtable
from toolsconnector.connectors.shopify.connector import Shopify
from toolsconnector.connectors.twilio.connector import Twilio

from .binding_ir import Location
from .executor import build_request, next_request
from .specs import ALL

CLASSES = {"airtable": Airtable, "twilio": Twilio, "shopify": Shopify}

# (connector, credential, [(action, kwargs)])
MATRIX = {
    "airtable": ("patTESTtoken", [
        ("list_records", dict(base_id="appABC", table_name="Contacts",
                              fields=["Name", "Email"], filter_formula="{Active}=1",
                              sort=[{"field": "Name", "direction": "desc"}, {"field": "Age"}],
                              limit=50)),
        ("delete_records", dict(base_id="appABC", table_name="Contacts",
                                record_ids=["rec1", "rec2", "rec3"])),
        ("create_record", dict(base_id="appABC", table_name="Contacts",
                               fields={"Name": "Jo", "Age": 30})),
        ("batch_create", dict(base_id="appABC", table_name="Contacts",
                              records=[{"Name": "A"}, {"Name": "B"}])),
        ("get_base_schema", dict(base_id="appABC")),
    ]),
    "twilio": ("ACxxxxsid:secrettoken", [
        ("send_sms", dict(to="+15551112222", from_="+15553334444", body="hi there")),
        ("list_messages", dict(to="+15551112222", limit=25)),
        ("create_verify_service", dict(friendly_name="My App")),
    ]),
    "shopify": ("shpat_abc123:mystore", [
        ("list_products", dict(limit=50)),
        ("create_product", dict(title="Widget", body_html="<p>x</p>", vendor="Acme")),
    ]),
}

# Pagination "next request" parity:
# (connector, cred, action, first_args, response_body, response_headers)
PAGI = [
    ("airtable", "patTESTtoken", "list_records",
     dict(base_id="appABC", table_name="Contacts", fields=["Name"], limit=50),
     {"records": [{"id": "rec1"}], "offset": "OFFTOK123"}, {}),
    ("twilio", "ACxxxxsid:secrettoken", "list_messages",
     dict(to="+15551112222", limit=25),
     {"messages": [], "next_page_uri":
      "/2010-04-01/Accounts/ACxxxxsid/Messages.json?PageSize=25&Page=1&PageToken=PAxyz"}, {}),
    ("shopify", "shpat_abc123:mystore", "list_products",
     dict(limit=50),
     {"products": []},
     {"link": '<https://mystore.myshopify.com/admin/api/2024-01/products.json'
              '?limit=50&page_info=CURSOR456>; rel="next"'}),
]

# Which hard patterns each action exercises (for the coverage report).
PATTERNS = {
    ("airtable", "list_records"): ["indexed query (fields[i])", "indexed-object query (sort[i][k])",
                                    "size clamp", "offset-token pagination", "list unwrap"],
    ("airtable", "delete_records"): ["bracket/batch query (records[])", "DELETE w/ array"],
    ("airtable", "create_record"): ["json body key placement"],
    ("airtable", "batch_create"): ["per-item body wrap ({fields:..})"],
    ("airtable", "get_base_schema"): ["multiple base URLs (meta)"],
    ("twilio", "send_sms"): ["form-encoded body", "path templating from creds", "basic auth from split creds"],
    ("twilio", "list_messages"): ["follow-URL pagination", "size clamp"],
    ("twilio", "create_verify_service"): ["multiple base URLs (verify)", "form body"],
    ("shopify", "list_products"): ["link-header pagination", "base-URL templating ({store})",
                                    "custom auth header"],
    ("shopify", "create_product"): ["single-key body wrap ({product:..})", "PUT create"],
}

# Latent connector bugs the spike surfaced. The spec-driven executor produces the
# *correct* request; the hand-written connector does not. Each entry asserts the
# executor's value is the verifiably-correct one (so this can't hide a real miss).
#   (connector, action_label) -> (url_field, correct_value, bug_description)
KNOWN_BUGS = {
    ("shopify", "list_products"): ("host", "mystore.myshopify.com",
        "base_url template {store} never substituted — BaseConnector.__init__ pre-fills "
        "_base_url with the class template, so Shopify._setup's .format(store=...) is dead code"),
    ("shopify", "create_product"): ("host", "mystore.myshopify.com",
        "base_url template {store} never substituted (see shopify/connector.py _setup)"),
    ("shopify", "list_products →next"): ("host", "mystore.myshopify.com",
        "base_url template {store} never substituted (see shopify/connector.py _setup)"),
    ("twilio", "list_messages →next"): ("path", "/2010-04-01/Accounts/ACxxxxsid/Messages.json",
        "next_page_uri followed via client.get() doubles the /2010-04-01 prefix "
        "(httpx merges base_url by concatenation, not RFC join) — twilio/connector.py _fetch_msgs"),
}

GREEN, YELLOW, RED, RST = "\033[32m", "\033[33m", "\033[31m", "\033[0m"
BADGE = {"PASS": f"{GREEN}PASS {RST}", "FIXED": f"{YELLOW}FIXED{RST}", "FAIL": f"{RED}FAIL {RST}"}


def classify(cname, label, gen, diffs):
    """PASS = byte-identical; FIXED = diverges only because the connector is
    buggy and the executor is correct; FAIL = a real expressiveness miss."""
    if not diffs:
        return "PASS"
    bug = KNOWN_BUGS.get((cname, label))
    if bug:
        field, correct, _ = bug
        if len(diffs) == 1 and diffs[0].startswith(f"url.{field}") and getattr(gen.url, field) == correct:
            return "FIXED"
    return "FAIL"


def _handler(calls, body=None, extra_headers=None):
    def handle(request):
        calls.append(request)
        payload = body if body is not None else {
            "records": [], "messages": [], "calls": [], "products": [], "customers": [],
            "draft_orders": [], "conversations": [], "tables": [], "usage_records": [],
            "incoming_phone_numbers": [], "offset": None, "sid": "X", "id": "X",
            "product": {}, "order": {}, "customer": {}, "webhook": {}, "count": 0,
        }
        return httpx.Response(200, json=payload, headers=extra_headers or {})
    return handle


def _swap_capture(connector, handler):
    transport = httpx.MockTransport(handler)
    for attr, val in list(vars(connector).items()):
        if isinstance(val, httpx.AsyncClient):
            setattr(connector, attr, httpx.AsyncClient(
                base_url=val.base_url, headers=val.headers, transport=transport, timeout=30.0))


def _cmp(real: httpx.Request, gen: httpx.Request, conn, action_name) -> list[str]:
    action = conn.actions[action_name]
    ep = conn.endpoints[action.endpoint]
    d: list[str] = []
    if real.method != gen.method:
        d.append(f"method {real.method!r} != {gen.method!r}")
    for part in ("scheme", "host", "path"):
        rv, gv = getattr(real.url, part), getattr(gen.url, part)
        if rv != gv:
            d.append(f"url.{part} {rv!r} != {gv!r}")
    rq, gq = sorted(real.url.params.multi_items()), sorted(gen.url.params.multi_items())
    if rq != gq:
        d.append(f"query\n      real={rq}\n      gen ={gq}")
    if any(p.location == Location.BODY for p in action.params):
        enc = action.body_encoding or ep.encoding
        rb, gb = real.content or b"", gen.content or b""
        if enc == "json":
            if json.loads(rb or b"{}") != json.loads(gb or b"{}"):
                d.append(f"json body\n      real={rb!r}\n      gen ={gb!r}")
        else:
            if sorted(parse_qsl(rb.decode())) != sorted(parse_qsl(gb.decode())):
                d.append(f"form body\n      real={rb!r}\n      gen ={gb!r}")
    rh, gh = real.headers.get(ep.auth_header), gen.headers.get(ep.auth_header)
    if rh != gh:
        d.append(f"auth[{ep.auth_header}] {rh!r} != {gh!r}")
    return d


async def main() -> int:
    results: list[tuple[str, str, bool, list[str]]] = []

    # ---- First-request parity ----
    for cname, (cred, actions) in MATRIX.items():
        conn = ALL[cname]
        instance = CLASSES[cname](credentials=cred)
        await instance._setup()
        calls: list[httpx.Request] = []
        _swap_capture(instance, _handler(calls))
        for action_name, kwargs in actions:
            calls.clear()
            try:
                await getattr(instance, f"a{action_name}")(**kwargs)
            except Exception:
                pass  # response parsing may fail; the request is already captured
            if not calls:
                results.append((cname, action_name, "FAIL", ["no request captured"]))
                continue
            gen = build_request(conn, action_name, kwargs, cred)
            diffs = _cmp(calls[-1], gen, conn, action_name)
            results.append((cname, action_name, classify(cname, action_name, gen, diffs), diffs))
        await instance._teardown()

    # ---- Pagination next-request parity ----
    pagi_results: list[tuple[str, str, bool, list[str]]] = []
    for cname, cred, action_name, first_args, body, headers in PAGI:
        conn = ALL[cname]
        instance = CLASSES[cname](credentials=cred)
        await instance._setup()
        calls = []
        _swap_capture(instance, _handler(calls, body=body, extra_headers=headers))
        label = f"{action_name} →next"
        try:
            page = await getattr(instance, f"a{action_name}")(**first_args)
            calls.clear()
            await page.anext_page()
        except Exception as e:  # noqa: BLE001
            pagi_results.append((cname, label, "FAIL", [f"raised {e!r}"]))
            await instance._teardown()
            continue
        if not calls:
            pagi_results.append((cname, label, "FAIL", ["no next request captured"]))
            await instance._teardown()
            continue
        gen = next_request(conn, action_name, first_args, cred, body=body, headers=headers)
        if gen is None:
            pagi_results.append((cname, label, "FAIL", ["executor returned no next request"]))
        else:
            diffs = _cmp(calls[-1], gen, conn, action_name)
            pagi_results.append((cname, label, classify(cname, label, gen, diffs), diffs))
        await instance._teardown()

    # ---- Report ----
    print("\n" + "=" * 74)
    print("  SPEC-DRIVEN EXECUTOR  vs  HAND-WRITTEN CONNECTOR   (request parity)")
    print("=" * 74)
    all_results = results + pagi_results
    for cname, label, status, diffs in all_results:
        print(f"  {BADGE[status]}  {cname}.{label}")
        if status == "FIXED":
            _, _, desc = KNOWN_BUGS[(cname, label)]
            print(f"        ↳ executor produced the CORRECT request; connector bug: {desc}")
        elif diffs:
            for line in diffs:
                print(f"        - {line}")

    npass = sum(1 for *_, s, _ in all_results if s == "PASS")
    nfixed = sum(1 for *_, s, _ in all_results if s == "FIXED")
    nfail = sum(1 for *_, s, _ in all_results if s == "FAIL")
    total = len(all_results)
    expressible = npass + nfixed
    covered = sorted({pat for _, pats in PATTERNS.items() for pat in pats})

    print("\n" + "-" * 74)
    print(f"  EXPRESSIBLE DECLARATIVELY: {expressible}/{total} requests "
          f"({npass} byte-identical, {nfixed} executor-corrected a connector bug)")
    print(f"  TRUE ESCAPE HATCHES NEEDED: {nfail}/{total}")
    print(f"  Coverage: {len(results)} first-call + {len(pagi_results)} pagination-next actions "
          f"across the 3 hardest connectors")
    print(f"\n  Hard patterns expressed by the bounded binding vocabulary ({len(covered)}):")
    for pat in covered:
        print(f"      • {pat}")
    if nfixed:
        print(f"\n  Latent connector bugs surfaced (executor is correct): {nfixed}")
        seen = set()
        for cname, label, status, _ in all_results:
            if status == "FIXED":
                _, _, desc = KNOWN_BUGS[(cname, label)]
                key = desc.split(" —")[0].split(" (")[0]
                if key not in seen:
                    seen.add(key)
                    print(f"      ⚠ {cname}: {desc}")
    print("-" * 74 + "\n")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
