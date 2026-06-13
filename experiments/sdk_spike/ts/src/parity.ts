// AUTO-GENERATED parity harness. Builds requests via the TS runtime and prints JSONL.
import { buildRequest } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";
import { AIRTABLE_BINDING } from "./airtable.ts";
import { TWILIO_BINDING } from "./twilio.ts";
import { SHOPIFY_BINDING } from "./shopify.ts";
import { STRIPE_BINDING } from "./stripe.ts";

const B: Record<string, ConnectorB> = { airtable: AIRTABLE_BINDING, twilio: TWILIO_BINDING, shopify: SHOPIFY_BINDING, stripe: STRIPE_BINDING };
const MATRIX = [
  {
    "connector": "airtable",
    "cred": "patTESTtoken",
    "action": "list_records",
    "args": {
      "base_id": "appABC",
      "table_name": "Contacts",
      "fields": [
        "Name",
        "Email"
      ],
      "filter_formula": "{Active}=1",
      "sort": [
        {
          "field": "Name",
          "direction": "desc"
        },
        {
          "field": "Age"
        }
      ],
      "limit": 50
    }
  },
  {
    "connector": "airtable",
    "cred": "patTESTtoken",
    "action": "delete_records",
    "args": {
      "base_id": "appABC",
      "table_name": "Contacts",
      "record_ids": [
        "rec1",
        "rec2",
        "rec3"
      ]
    }
  },
  {
    "connector": "airtable",
    "cred": "patTESTtoken",
    "action": "create_record",
    "args": {
      "base_id": "appABC",
      "table_name": "Contacts",
      "fields": {
        "Name": "Jo",
        "Age": 30
      }
    }
  },
  {
    "connector": "airtable",
    "cred": "patTESTtoken",
    "action": "batch_create",
    "args": {
      "base_id": "appABC",
      "table_name": "Contacts",
      "records": [
        {
          "Name": "A"
        },
        {
          "Name": "B"
        }
      ]
    }
  },
  {
    "connector": "airtable",
    "cred": "patTESTtoken",
    "action": "get_base_schema",
    "args": {
      "base_id": "appABC"
    }
  },
  {
    "connector": "twilio",
    "cred": "ACxxxxsid:secrettoken",
    "action": "send_sms",
    "args": {
      "to": "+15551112222",
      "from_": "+15553334444",
      "body": "hi there"
    }
  },
  {
    "connector": "twilio",
    "cred": "ACxxxxsid:secrettoken",
    "action": "list_messages",
    "args": {
      "to": "+15551112222",
      "limit": 25
    }
  },
  {
    "connector": "twilio",
    "cred": "ACxxxxsid:secrettoken",
    "action": "create_verify_service",
    "args": {
      "friendly_name": "My App"
    }
  },
  {
    "connector": "shopify",
    "cred": "shpat_abc123:mystore",
    "action": "list_products",
    "args": {
      "limit": 50
    }
  },
  {
    "connector": "shopify",
    "cred": "shpat_abc123:mystore",
    "action": "create_product",
    "args": {
      "title": "Widget",
      "body_html": "<p>x</p>",
      "vendor": "Acme"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_customers",
    "args": {
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_customer",
    "args": {
      "customer_id": "cus_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_customer",
    "args": {
      "email": "a@example.com",
      "name": "Alice",
      "description": "d"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "update_customer",
    "args": {
      "customer_id": "cus_1",
      "name": "New",
      "email": "b@example.com"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "delete_customer",
    "args": {
      "customer_id": "cus_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_charges",
    "args": {
      "customer": "cus_1",
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_charge",
    "args": {
      "charge_id": "ch_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_charge",
    "args": {
      "amount": 2000,
      "currency": "usd",
      "customer": "cus_1",
      "source": "tok_visa"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "refund_charge",
    "args": {
      "charge_id": "ch_1",
      "amount": 300,
      "reason": "requested_by_customer"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_refunds",
    "args": {
      "charge": "ch_1",
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_payment_intent",
    "args": {
      "amount": 1100,
      "currency": "usd",
      "customer": "cus_1",
      "payment_method_types": [
        "card",
        "link"
      ],
      "capture_method": "manual"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_payment_intent",
    "args": {
      "payment_intent_id": "pi_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_payment_intents",
    "args": {
      "customer": "cus_1",
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "confirm_payment_intent",
    "args": {
      "payment_intent_id": "pi_1",
      "payment_method": "pm_card_visa",
      "return_url": "https://example.com/back"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "cancel_payment_intent",
    "args": {
      "payment_intent_id": "pi_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "capture_payment_intent",
    "args": {
      "payment_intent_id": "pi_1",
      "amount_to_capture": 500
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_invoices",
    "args": {
      "customer": "cus_1",
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_invoice",
    "args": {
      "invoice_id": "in_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "void_invoice",
    "args": {
      "invoice_id": "in_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_balance",
    "args": {}
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_subscription",
    "args": {
      "customer": "cus_1",
      "price": "price_1",
      "trial_days": 7
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_subscriptions",
    "args": {
      "customer": "cus_1",
      "status": "all",
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_subscription",
    "args": {
      "subscription_id": "sub_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_product",
    "args": {
      "name": "Widget",
      "description": "x"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_products",
    "args": {
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_price",
    "args": {
      "product": "prod_1",
      "unit_amount": 999,
      "currency": "usd",
      "recurring_interval": "month"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_prices",
    "args": {
      "product": "prod_1",
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_checkout_session",
    "args": {
      "line_items": [
        {
          "price": "price_1",
          "quantity": 2
        }
      ],
      "mode": "payment",
      "success_url": "https://e.com/s",
      "cancel_url": "https://e.com/c"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_payment_methods",
    "args": {
      "customer": "cus_1",
      "type": "card",
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_disputes",
    "args": {
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_dispute",
    "args": {
      "dispute_id": "dp_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "close_dispute",
    "args": {
      "dispute_id": "dp_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_payouts",
    "args": {
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_payout",
    "args": {
      "amount": 100,
      "currency": "usd"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_payout",
    "args": {
      "payout_id": "po_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_events",
    "args": {
      "type": "charge.succeeded",
      "limit": 10
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_event",
    "args": {
      "event_id": "evt_1"
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "create_setup_intent",
    "args": {
      "customer": "cus_1",
      "payment_method_types": [
        "card"
      ]
    }
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "get_setup_intent",
    "args": {
      "setup_intent_id": "seti_1"
    }
  }
];

for (const m of MATRIX) {
  const r = buildRequest(B[m.connector], m.action, m.args as Record<string, unknown>, m.cred);
  console.log(JSON.stringify({
    connector: m.connector, action: m.action, method: r.method,
    host: r.host, path: r.path, query: r.query, body: r.body,
    contentType: r.contentType, auth: r.auth,
  }));
}
