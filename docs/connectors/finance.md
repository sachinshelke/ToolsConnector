# Finance & Payments

Connectors for payment processing and financial data services. 2 connectors, 57 actions.

---

### Stripe

**Category:** Finance & Payments | **Auth:** Secret Key (sk_) | **Actions:** 8

Connect to Stripe to manage customers, charges, payment intents, invoices, and account balances.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_customers | List customers with optional filters | No |
| get_customer | Get a specific customer by ID | No |
| create_customer | Create a new customer | Yes |
| list_charges | List charges with optional filters | No |
| get_charge | Get a specific charge by ID | No |
| create_payment_intent | Create a new payment intent | Yes |
| list_invoices | List invoices | No |
| get_balance | Get the current account balance | No |

**Quick start:**

```python
kit = ToolKit(["stripe"], credentials={"stripe": "sk_test_your-secret-key"})
result = kit.execute("stripe_list_customers", {"limit": 10})
```

---

### Plaid

**Category:** Finance & Payments | **Auth:** Client ID + Secret | **Actions:** 8

Connect to Plaid to access bank account data, transactions, balances, and institution information.

**Actions:**

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

**Quick start:**

```python
kit = ToolKit(["plaid"], credentials={"plaid": {"client_id": "your-client-id", "secret": "your-secret", "environment": "sandbox"}})
result = kit.execute("plaid_get_accounts", {"access_token": "access-sandbox-..."})
```
