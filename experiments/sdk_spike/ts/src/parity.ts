// AUTO-GENERATED parity harness. Builds requests via the TS runtime and prints JSONL.
import { buildRequest, nextRequest } from "./runtime.ts";
import type { BuiltRequest, ConnectorB } from "./runtime.ts";
import { AIRTABLE_BINDING } from "./airtable.ts";
import { TWILIO_BINDING } from "./twilio.ts";
import { SHOPIFY_BINDING } from "./shopify.ts";
import { STRIPE_BINDING } from "./stripe.ts";
import { GITHUB_BINDING } from "./github.ts";

const B: Record<string, ConnectorB> = { airtable: AIRTABLE_BINDING, twilio: TWILIO_BINDING, shopify: SHOPIFY_BINDING, stripe: STRIPE_BINDING, github: GITHUB_BINDING };
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
      "description": "d",
      "metadata": {
        "plan": "pro",
        "ref": "abc"
      }
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
      "description": "x",
      "metadata": {
        "sku": "X1"
      }
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
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_repos",
    "args": {
      "org": "acme",
      "limit": 50
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "get_repo",
    "args": {
      "owner": "octocat",
      "repo": "hello"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "create_repo",
    "args": {
      "name": "newrepo",
      "description": "d",
      "private": true,
      "org": "acme"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "fork_repo",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "organization": "myorg"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_issues",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "state": "open",
      "labels": "bug,p1",
      "assignee": "me",
      "limit": 25
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "create_issue",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "title": "Bug",
      "body": "desc",
      "labels": [
        "bug"
      ],
      "assignees": [
        "me"
      ]
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "get_issue",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "issue_number": 42
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "update_issue",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "issue_number": 42,
      "title": "New",
      "state": "closed",
      "labels": [
        "wontfix"
      ]
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "add_labels",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "issue_number": 42,
      "labels": [
        "bug",
        "p1"
      ]
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "remove_label",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "issue_number": 42,
      "label_name": "bug"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "create_comment",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "issue_number": 42,
      "body": "comment"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_comments",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "issue_number": 42,
      "limit": 50
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_pull_requests",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "state": "open",
      "limit": 20
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "get_pull_request",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "pr_number": 7
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "create_pull_request",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "title": "PR",
      "head": "feat",
      "base": "main",
      "body": "b",
      "draft": true
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "merge_pull_request",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "pr_number": 7,
      "merge_method": "squash",
      "commit_title": "merge"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_commits",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "sha": "main",
      "path": "src",
      "author": "me",
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_branches",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "get_branch",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "branch": "main"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_releases",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "get_latest_release",
    "args": {
      "owner": "octocat",
      "repo": "hello"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "create_release",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "tag_name": "v1.0",
      "name": "Release",
      "body": "notes",
      "draft": false,
      "prerelease": true,
      "target_commitish": "main"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "get_content",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "path": "README.md",
      "ref": "main"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "create_or_update_file",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "path": "README.md",
      "content": "aGVsbG8=",
      "message": "commit",
      "sha": "abc",
      "branch": "main"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "delete_file",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "path": "old.txt",
      "sha": "abc",
      "message": "rm",
      "branch": "main"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_workflows",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_workflow_runs",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "workflow_id": "123",
      "branch": "main",
      "status": "completed",
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "trigger_workflow",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "workflow_id": "123",
      "ref": "main",
      "inputs": {
        "env": "prod"
      }
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_gists",
    "args": {
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "search_code",
    "args": {
      "query": "addClass repo:jquery/jquery",
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "search_repos",
    "args": {
      "query": "tetris language:python",
      "sort": "stars",
      "order": "desc",
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "search_issues",
    "args": {
      "query": "windows label:bug",
      "sort": "created",
      "order": "asc",
      "limit": 10
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "get_authenticated_user",
    "args": {}
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "get_rate_limit",
    "args": {}
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "star_repo",
    "args": {
      "owner": "octocat",
      "repo": "hello"
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "unstar_repo",
    "args": {
      "owner": "octocat",
      "repo": "hello"
    }
  }
];
const PAGI = [
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_customers",
    "args": {
      "limit": 10
    },
    "body": {
      "data": [
        {
          "id": "cus_A"
        },
        {
          "id": "cus_LAST"
        }
      ],
      "has_more": true
    },
    "headers": {}
  },
  {
    "connector": "stripe",
    "cred": "sk_test_FAKE",
    "action": "list_charges",
    "args": {
      "customer": "cus_1",
      "limit": 10
    },
    "body": {
      "data": [
        {
          "id": "ch_LAST"
        }
      ],
      "has_more": true
    },
    "headers": {}
  },
  {
    "connector": "airtable",
    "cred": "patTESTtoken",
    "action": "list_records",
    "args": {
      "base_id": "appABC",
      "table_name": "Contacts",
      "fields": [
        "Name"
      ],
      "limit": 50
    },
    "body": {
      "records": [
        {
          "id": "rec1"
        }
      ],
      "offset": "OFFTOK123"
    },
    "headers": {}
  },
  {
    "connector": "twilio",
    "cred": "ACxxxxsid:secrettoken",
    "action": "list_messages",
    "args": {
      "to": "+15551112222",
      "limit": 25
    },
    "body": {
      "messages": [],
      "next_page_uri": "/2010-04-01/Accounts/ACxxxxsid/Messages.json?PageSize=25&Page=1&PageToken=PAxyz"
    },
    "headers": {}
  },
  {
    "connector": "shopify",
    "cred": "shpat_abc123:mystore",
    "action": "list_products",
    "args": {
      "limit": 50
    },
    "body": {
      "products": []
    },
    "headers": {
      "link": "<https://mystore.myshopify.com/admin/api/2024-01/products.json?limit=50&page_info=CURSOR456>; rel=\"next\""
    }
  },
  {
    "connector": "github",
    "cred": "ghp_TESTtoken",
    "action": "list_issues",
    "args": {
      "owner": "octocat",
      "repo": "hello",
      "limit": 25
    },
    "body": {},
    "headers": {
      "link": "<https://api.github.com/repositories/123/issues?per_page=25&page=2>; rel=\"next\""
    }
  }
];

function emit(kind: string, connector: string, action: string, r: BuiltRequest | null) {
  if (!r) { console.log(JSON.stringify({ kind, connector, action, none: true })); return; }
  console.log(JSON.stringify({
    kind, connector, action, method: r.method, host: r.host, path: r.path,
    query: r.query, body: r.body, contentType: r.contentType, auth: r.auth,
  }));
}

for (const m of MATRIX) {
  emit("first", m.connector, m.action,
       buildRequest(B[m.connector], m.action, m.args as Record<string, unknown>, m.cred));
}
for (const m of PAGI) {
  emit("next", m.connector, m.action, nextRequest(
    B[m.connector], m.action, m.args as Record<string, unknown>, m.cred,
    m.body as Record<string, unknown>, m.headers as Record<string, string>));
}
