# Finance & Payments

Connectors for payment processing and financial data services. 2 connectors, 57 actions.

---

### Stripe

**Category:** Finance & Payments | **Auth:** Secret Key (sk_) | **Actions:** 40 | **Verification:** ✅ Tier 1 (Live verified — 38/40 happy-path + 2/40 envelope, test mode; payouts need a bank account configured)

Connect to Stripe for the full payment lifecycle: customers, PaymentIntents (create / confirm / capture / cancel), charges and refunds, subscriptions, products and prices, invoices, Checkout Sessions, SetupIntents, payment methods, disputes, payouts, events, and account balance.

**Actions (40 total — sample):**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| create_customer | Create a new Stripe customer | Yes |
| create_payment_intent | Create a Stripe PaymentIntent | Yes |
| confirm_payment_intent | Confirm a Stripe PaymentIntent | Yes |
| capture_payment_intent | Capture a Stripe PaymentIntent | Yes |
| refund_charge | Refund a charge | Yes |
| create_subscription | Create a subscription | Yes |
| create_checkout_session | Create a Stripe Checkout Session | Yes |
| get_balance | Retrieve the current Stripe account balance | No |
| … | +32 more actions — see the connector README | |

**Quick start:**

```python
kit = ToolKit(["stripe"], credentials={"stripe": "sk_test_your-secret-key"})
result = kit.execute("stripe_create_payment_intent", {
    "amount": 1100, "currency": "usd", "payment_method_types": ["card"],
})
```

---

### Plaid

**Category:** Finance & Payments | **Auth:** Client ID + Secret | **Actions:** 17

Connect to Plaid to access bank account data, transactions, balances, identity, liabilities, investments, and institution information.

**Actions (17 total — sample):**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| get_accounts | Get linked bank accounts | No |
| get_transactions | Get transactions for a date range | No |
| get_balance | Get real-time account balances | No |
| get_identity | Get account holder identity information | No |
| get_institution | Get details of a specific institution | No |
| search_institutions | Search for financial institutions | No |
| create_link_token | Create a Link token for Plaid Link | No |
| exchange_public_token | Exchange a public token for an access token | No |
| … | +9 more actions — see the connector README | |

**Quick start:**

```python
kit = ToolKit(["plaid"], credentials={"plaid": {"client_id": "your-client-id", "secret": "your-secret", "environment": "sandbox"}})
result = kit.execute("plaid_get_accounts", {"access_token": "access-sandbox-..."})
```
