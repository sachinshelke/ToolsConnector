# @toolsconnector/sdk

In-process, **bring-your-own-key** TypeScript SDK for [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) connectors. Generated from the same declarative bindings as the Python SDK — every request is **byte-identical** to the live-verified Python connector (proven by a cross-language parity gate).

First connector: **Stripe** (Tier-1, live-verified — 40/40 actions).

> No server, nothing hosted. The SDK runs in your process and calls the vendor API directly with your key.

## Install

```bash
npm install @toolsconnector/sdk
```

## Usage

```ts
import { Stripe, paginate, STRIPE_BINDING } from "@toolsconnector/sdk";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

// Any of the 40 actions — typed args, idiomatic camelCase.
const customer = await stripe.createCustomer({
  email: "a@example.com",
  name: "Acme",
  metadata: { plan: "pro" },          // dynamic-key maps are supported
});

const pi = await stripe.createPaymentIntent({
  amount: 1100, currency: "usd",
  paymentMethodTypes: ["card"],
});

// Cursor pagination — walk every page lazily.
for await (const c of paginate(STRIPE_BINDING, "list_customers", { limit: 50 }, key)) {
  console.log(c);
}
```

## Escape hatches

A tiny minority of actions (e.g. `cancel_subscription`, whose HTTP method switches on an argument) aren't declaratively expressible. They're present as typed methods that delegate to an override you supply:

```ts
const stripe = new Stripe(key, {
  overrides: {
    cancel_subscription: async (cred, args) => { /* your impl */ },
  },
});
await stripe.cancelSubscription({ subscription_id: "sub_123" });
```

## How it's built

The connector files (`src/stripe.ts`, `src/runtime.ts`) are **generated** from ToolsConnector's binding IR and verified byte-for-byte against the Python connector. Do not hand-edit them — regenerate from the source bindings.

## License

Apache-2.0
