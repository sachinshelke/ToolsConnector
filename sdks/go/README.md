# toolsconnector — Go SDK

In-process, **bring-your-own-key** Go SDK for [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) connectors. Generated from the same declarative bindings as the Python and TypeScript SDKs — every request is **byte-identical** across all three languages (proven by a cross-language parity gate).

First connector: **Stripe** (Tier-1, live-verified — 40/40 actions).

> No server, nothing hosted. The SDK runs in your process and calls the vendor API directly with your key.

## Install

```bash
go get github.com/sachinshelke/ToolsConnector/sdks/go
```

## Usage

```go
package main

import (
	"fmt"

	tc "github.com/sachinshelke/ToolsConnector/sdks/go"
)

func main() {
	s := tc.NewStripe("sk_test_...")

	email := "a@example.com"
	customer, err := s.CreateCustomer(tc.CreateCustomerArgs{
		Email:    &email,
		Metadata: map[string]string{"plan": "pro"}, // dynamic-key maps supported
	})
	if err != nil {
		panic(err)
	}
	fmt.Println(customer)

	// Cursor pagination — walk every page.
	limit := 50
	all, err := s.ListCustomersAll(tc.ListCustomersArgs{Limit: &limit})
	if err != nil {
		panic(err)
	}
	fmt.Printf("%d customers\n", len(all))
}
```

Optional scalar arguments are pointers (`*string`, `*int`) so "absent" is distinct from a zero value; required path arguments and collection arguments (`[]string`, `map[string]string`) are passed by value.

## Custom HTTP client

Inject your own `*http.Client` (timeouts, proxies, or a test transport):

```go
s := tc.NewStripe(key, tc.StripeWithHTTPClient(&http.Client{Timeout: 30 * time.Second}))
```

## Escape hatches

A tiny minority of actions (e.g. `cancel_subscription`, whose HTTP method switches on an argument) aren't declaratively expressible. They're present as typed methods that delegate to an override you register:

```go
s := tc.NewStripe(key, tc.StripeWithOverride("cancel_subscription",
	func(cred string, args map[string]any) (any, error) {
		// your impl
		return nil, nil
	}))
_, _ = s.CancelSubscription(map[string]any{"subscription_id": "sub_123"})
```

## How it's built

`runtime.go` is the thin, hand-written interpreter (the Go sibling of the Python executor / TS runtime). `stripe.go` is **generated** from ToolsConnector's binding IR and verified byte-for-byte against the Python connector. Do not hand-edit `stripe.go` — regenerate from the source bindings.

## License

Apache-2.0
