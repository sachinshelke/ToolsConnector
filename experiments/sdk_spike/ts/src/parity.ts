// AUTO-GENERATED parity harness. Builds requests via the TS runtime and prints JSONL.
import { buildRequest } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";
import { AIRTABLE_BINDING } from "./airtable.ts";
import { TWILIO_BINDING } from "./twilio.ts";
import { SHOPIFY_BINDING } from "./shopify.ts";

const B: Record<string, ConnectorB> = { airtable: AIRTABLE_BINDING, twilio: TWILIO_BINDING, shopify: SHOPIFY_BINDING };
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
