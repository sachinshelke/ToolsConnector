// End-to-end test of the GENERATED Stripe SDK (not just request-shape parity):
// drives the real generated class + runtime against a mock fetch, exercising a
// create-with-metadata, true multi-page pagination, and the escape-hatch override.
//   Run:  node experiments/sdk_spike/ts/src/e2e.ts
import { STRIPE_BINDING, Stripe } from "../src/stripe.ts";
import { paginate } from "../src/runtime.ts";

const calls: { url: string; method: string; body: string | null }[] = [];
let pages: Record<string, unknown>[] = [];
let pageIdx = 0;

(globalThis as unknown as { fetch: unknown }).fetch = async (url: string, opts: { method: string; body?: string }) => {
  calls.push({ url, method: opts.method, body: opts.body ?? null });
  const isList = url.includes("/customers") && opts.method === "GET";
  const body = isList ? pages[Math.min(pageIdx++, pages.length - 1)] : { id: "obj_1" };
  return { json: async () => body, headers: new Map<string, string>() };
};

let fails = 0;
const check = (cond: boolean, msg: string) => {
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${msg}`);
  if (!cond) fails++;
};

(async () => {
  const cred = "sk_test_FAKE";
  const stripe = new Stripe(cred, {
    overrides: {
      cancel_subscription: async (_c: string, args: Record<string, unknown>) =>
        ({ canceled: true, id: args.subscription_id }),
    },
  });

  // 1. create with metadata -> real POST with flattened metadata body
  calls.length = 0;
  await stripe.createCustomer({ email: "a@b.com", name: "A", metadata: { plan: "pro" } } as never);
  check(calls[0]?.method === "POST" && calls[0].url.endsWith("/v1/customers"), "createCustomer -> POST /v1/customers");
  check((calls[0]?.body ?? "").includes("metadata%5Bplan%5D=pro"), "metadata flattened into body");

  // 2. paginate() walks all pages via the LAST_ID cursor
  calls.length = 0; pageIdx = 0;
  pages = [
    { data: [{ id: "cus_1" }, { id: "cus_2" }], has_more: true },
    { data: [{ id: "cus_3" }], has_more: false },
  ];
  const items: unknown[] = [];
  for await (const it of paginate(STRIPE_BINDING, "list_customers", { limit: 2 }, cred)) items.push(it);
  check(items.length === 3, `paginate walked every page (got ${items.length} items)`);
  check(calls.length === 2, `made exactly 2 requests (made ${calls.length})`);
  check((calls[1]?.url ?? "").includes("starting_after=cus_2"), "page 2 cursor = last id (starting_after=cus_2)");

  // 3. escape-hatch action present + delegates to the override
  const r = (await stripe.cancelSubscription({ subscription_id: "sub_1" })) as { canceled: boolean; id: string };
  check(r.canceled === true && r.id === "sub_1", "cancelSubscription -> override ran");

  console.log(fails ? `\n  ${fails} E2E CHECK(S) FAILED` : "\n  ALL E2E CHECKS PASS — generated Stripe SDK works end-to-end");
  process.exit(fails ? 1 : 0);
})();
