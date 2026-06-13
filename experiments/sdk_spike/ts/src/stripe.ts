// AUTO-GENERATED from the connector binding. Do not edit by hand.
import { execute } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";

export const STRIPE_BINDING: ConnectorB = {
  "name": "stripe",
  "endpoints": {
    "main": {
      "id": "main",
      "baseUrl": "https://api.stripe.com/v1",
      "encoding": "form",
      "authKind": "basic_user",
      "authHeader": "Authorization"
    }
  },
  "defaultEndpoint": "main",
  "actions": {
    "list_customers": {
      "name": "list_customers",
      "method": "GET",
      "endpoint": "main",
      "path": "/customers",
      "params": [
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "get_customer": {
      "name": "get_customer",
      "method": "GET",
      "endpoint": "main",
      "path": "/customers/{customer_id}",
      "params": [
        {
          "name": "customer_id",
          "wire": "customer_id",
          "location": "path"
        }
      ]
    },
    "create_customer": {
      "name": "create_customer",
      "method": "POST",
      "endpoint": "main",
      "path": "/customers",
      "params": [
        {
          "name": "email",
          "wire": "email",
          "location": "body"
        },
        {
          "name": "name",
          "wire": "name",
          "location": "body"
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body"
        }
      ]
    },
    "update_customer": {
      "name": "update_customer",
      "method": "POST",
      "endpoint": "main",
      "path": "/customers/{customer_id}",
      "params": [
        {
          "name": "customer_id",
          "wire": "customer_id",
          "location": "path"
        },
        {
          "name": "email",
          "wire": "email",
          "location": "body"
        },
        {
          "name": "name",
          "wire": "name",
          "location": "body"
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body"
        }
      ]
    },
    "delete_customer": {
      "name": "delete_customer",
      "method": "DELETE",
      "endpoint": "main",
      "path": "/customers/{customer_id}",
      "params": [
        {
          "name": "customer_id",
          "wire": "customer_id",
          "location": "path"
        }
      ]
    },
    "list_charges": {
      "name": "list_charges",
      "method": "GET",
      "endpoint": "main",
      "path": "/charges",
      "params": [
        {
          "name": "customer",
          "wire": "customer",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "get_charge": {
      "name": "get_charge",
      "method": "GET",
      "endpoint": "main",
      "path": "/charges/{charge_id}",
      "params": [
        {
          "name": "charge_id",
          "wire": "charge_id",
          "location": "path"
        }
      ]
    },
    "create_charge": {
      "name": "create_charge",
      "method": "POST",
      "endpoint": "main",
      "path": "/charges",
      "params": [
        {
          "name": "amount",
          "wire": "amount",
          "location": "body"
        },
        {
          "name": "currency",
          "wire": "currency",
          "location": "body"
        },
        {
          "name": "customer",
          "wire": "customer",
          "location": "body"
        },
        {
          "name": "source",
          "wire": "source",
          "location": "body"
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body"
        }
      ]
    },
    "refund_charge": {
      "name": "refund_charge",
      "method": "POST",
      "endpoint": "main",
      "path": "/refunds",
      "params": [
        {
          "name": "charge_id",
          "wire": "charge",
          "location": "body"
        },
        {
          "name": "amount",
          "wire": "amount",
          "location": "body"
        },
        {
          "name": "reason",
          "wire": "reason",
          "location": "body"
        }
      ]
    },
    "list_refunds": {
      "name": "list_refunds",
      "method": "GET",
      "endpoint": "main",
      "path": "/refunds",
      "params": [
        {
          "name": "charge",
          "wire": "charge",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "create_payment_intent": {
      "name": "create_payment_intent",
      "method": "POST",
      "endpoint": "main",
      "path": "/payment_intents",
      "params": [
        {
          "name": "amount",
          "wire": "amount",
          "location": "body"
        },
        {
          "name": "currency",
          "wire": "currency",
          "location": "body"
        },
        {
          "name": "customer",
          "wire": "customer",
          "location": "body"
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body"
        },
        {
          "name": "payment_method_types",
          "wire": "payment_method_types",
          "location": "body",
          "style": "indexed"
        },
        {
          "name": "payment_method",
          "wire": "payment_method",
          "location": "body"
        },
        {
          "name": "capture_method",
          "wire": "capture_method",
          "location": "body"
        }
      ]
    },
    "get_payment_intent": {
      "name": "get_payment_intent",
      "method": "GET",
      "endpoint": "main",
      "path": "/payment_intents/{payment_intent_id}",
      "params": [
        {
          "name": "payment_intent_id",
          "wire": "payment_intent_id",
          "location": "path"
        }
      ]
    },
    "list_payment_intents": {
      "name": "list_payment_intents",
      "method": "GET",
      "endpoint": "main",
      "path": "/payment_intents",
      "params": [
        {
          "name": "customer",
          "wire": "customer",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "confirm_payment_intent": {
      "name": "confirm_payment_intent",
      "method": "POST",
      "endpoint": "main",
      "path": "/payment_intents/{payment_intent_id}/confirm",
      "params": [
        {
          "name": "payment_intent_id",
          "wire": "payment_intent_id",
          "location": "path"
        },
        {
          "name": "payment_method",
          "wire": "payment_method",
          "location": "body"
        },
        {
          "name": "return_url",
          "wire": "return_url",
          "location": "body"
        }
      ]
    },
    "cancel_payment_intent": {
      "name": "cancel_payment_intent",
      "method": "POST",
      "endpoint": "main",
      "path": "/payment_intents/{payment_intent_id}/cancel",
      "params": [
        {
          "name": "payment_intent_id",
          "wire": "payment_intent_id",
          "location": "path"
        }
      ]
    },
    "capture_payment_intent": {
      "name": "capture_payment_intent",
      "method": "POST",
      "endpoint": "main",
      "path": "/payment_intents/{payment_intent_id}/capture",
      "params": [
        {
          "name": "payment_intent_id",
          "wire": "payment_intent_id",
          "location": "path"
        },
        {
          "name": "amount_to_capture",
          "wire": "amount_to_capture",
          "location": "body"
        }
      ]
    },
    "list_invoices": {
      "name": "list_invoices",
      "method": "GET",
      "endpoint": "main",
      "path": "/invoices",
      "params": [
        {
          "name": "customer",
          "wire": "customer",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "get_invoice": {
      "name": "get_invoice",
      "method": "GET",
      "endpoint": "main",
      "path": "/invoices/{invoice_id}",
      "params": [
        {
          "name": "invoice_id",
          "wire": "invoice_id",
          "location": "path"
        }
      ]
    },
    "void_invoice": {
      "name": "void_invoice",
      "method": "POST",
      "endpoint": "main",
      "path": "/invoices/{invoice_id}/void",
      "params": [
        {
          "name": "invoice_id",
          "wire": "invoice_id",
          "location": "path"
        }
      ]
    },
    "get_balance": {
      "name": "get_balance",
      "method": "GET",
      "endpoint": "main",
      "path": "/balance",
      "params": []
    },
    "create_subscription": {
      "name": "create_subscription",
      "method": "POST",
      "endpoint": "main",
      "path": "/subscriptions",
      "params": [
        {
          "name": "customer",
          "wire": "customer",
          "location": "body"
        },
        {
          "name": "price",
          "wire": "items[0][price]",
          "location": "body"
        },
        {
          "name": "trial_days",
          "wire": "trial_period_days",
          "location": "body"
        }
      ]
    },
    "list_subscriptions": {
      "name": "list_subscriptions",
      "method": "GET",
      "endpoint": "main",
      "path": "/subscriptions",
      "params": [
        {
          "name": "customer",
          "wire": "customer",
          "location": "query"
        },
        {
          "name": "status",
          "wire": "status",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "get_subscription": {
      "name": "get_subscription",
      "method": "GET",
      "endpoint": "main",
      "path": "/subscriptions/{subscription_id}",
      "params": [
        {
          "name": "subscription_id",
          "wire": "subscription_id",
          "location": "path"
        }
      ]
    },
    "create_product": {
      "name": "create_product",
      "method": "POST",
      "endpoint": "main",
      "path": "/products",
      "params": [
        {
          "name": "name",
          "wire": "name",
          "location": "body"
        },
        {
          "name": "description",
          "wire": "description",
          "location": "body"
        }
      ]
    },
    "list_products": {
      "name": "list_products",
      "method": "GET",
      "endpoint": "main",
      "path": "/products",
      "params": [
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "create_price": {
      "name": "create_price",
      "method": "POST",
      "endpoint": "main",
      "path": "/prices",
      "params": [
        {
          "name": "product",
          "wire": "product",
          "location": "body"
        },
        {
          "name": "unit_amount",
          "wire": "unit_amount",
          "location": "body"
        },
        {
          "name": "currency",
          "wire": "currency",
          "location": "body"
        },
        {
          "name": "recurring_interval",
          "wire": "recurring[interval]",
          "location": "body"
        }
      ]
    },
    "list_prices": {
      "name": "list_prices",
      "method": "GET",
      "endpoint": "main",
      "path": "/prices",
      "params": [
        {
          "name": "product",
          "wire": "product",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "create_checkout_session": {
      "name": "create_checkout_session",
      "method": "POST",
      "endpoint": "main",
      "path": "/checkout/sessions",
      "params": [
        {
          "name": "mode",
          "wire": "mode",
          "location": "body"
        },
        {
          "name": "success_url",
          "wire": "success_url",
          "location": "body"
        },
        {
          "name": "cancel_url",
          "wire": "cancel_url",
          "location": "body"
        },
        {
          "name": "line_items",
          "wire": "line_items",
          "location": "body",
          "style": "indexed_object",
          "subkeys": [
            "price",
            "quantity"
          ],
          "subkeyDefaults": {
            "quantity": 1
          }
        }
      ]
    },
    "list_payment_methods": {
      "name": "list_payment_methods",
      "method": "GET",
      "endpoint": "main",
      "path": "/payment_methods",
      "params": [
        {
          "name": "customer",
          "wire": "customer",
          "location": "query"
        },
        {
          "name": "type",
          "wire": "type",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "list_disputes": {
      "name": "list_disputes",
      "method": "GET",
      "endpoint": "main",
      "path": "/disputes",
      "params": [
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "get_dispute": {
      "name": "get_dispute",
      "method": "GET",
      "endpoint": "main",
      "path": "/disputes/{dispute_id}",
      "params": [
        {
          "name": "dispute_id",
          "wire": "dispute_id",
          "location": "path"
        }
      ]
    },
    "close_dispute": {
      "name": "close_dispute",
      "method": "POST",
      "endpoint": "main",
      "path": "/disputes/{dispute_id}/close",
      "params": [
        {
          "name": "dispute_id",
          "wire": "dispute_id",
          "location": "path"
        }
      ]
    },
    "list_payouts": {
      "name": "list_payouts",
      "method": "GET",
      "endpoint": "main",
      "path": "/payouts",
      "params": [
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "create_payout": {
      "name": "create_payout",
      "method": "POST",
      "endpoint": "main",
      "path": "/payouts",
      "params": [
        {
          "name": "amount",
          "wire": "amount",
          "location": "body"
        },
        {
          "name": "currency",
          "wire": "currency",
          "location": "body"
        }
      ]
    },
    "get_payout": {
      "name": "get_payout",
      "method": "GET",
      "endpoint": "main",
      "path": "/payouts/{payout_id}",
      "params": [
        {
          "name": "payout_id",
          "wire": "payout_id",
          "location": "path"
        }
      ]
    },
    "list_events": {
      "name": "list_events",
      "method": "GET",
      "endpoint": "main",
      "path": "/events",
      "params": [
        {
          "name": "type",
          "wire": "type",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 10,
          "max": 100
        },
        {
          "name": "starting_after",
          "wire": "starting_after",
          "location": "query"
        }
      ],
      "unwrap": "data"
    },
    "get_event": {
      "name": "get_event",
      "method": "GET",
      "endpoint": "main",
      "path": "/events/{event_id}",
      "params": [
        {
          "name": "event_id",
          "wire": "event_id",
          "location": "path"
        }
      ]
    },
    "create_setup_intent": {
      "name": "create_setup_intent",
      "method": "POST",
      "endpoint": "main",
      "path": "/setup_intents",
      "params": [
        {
          "name": "customer",
          "wire": "customer",
          "location": "body"
        },
        {
          "name": "payment_method_types",
          "wire": "payment_method_types",
          "location": "body",
          "style": "indexed"
        }
      ]
    },
    "get_setup_intent": {
      "name": "get_setup_intent",
      "method": "GET",
      "endpoint": "main",
      "path": "/setup_intents/{setup_intent_id}",
      "params": [
        {
          "name": "setup_intent_id",
          "wire": "setup_intent_id",
          "location": "path"
        }
      ]
    }
  }
};

export interface ListCustomersArgs {
  limit?: number;
  starting_after?: string;
}

export interface GetCustomerArgs {
  customer_id: string;
}

export interface CreateCustomerArgs {
  email?: string;
  name?: string;
  description?: string;
}

export interface UpdateCustomerArgs {
  customer_id: string;
  email?: string;
  name?: string;
  description?: string;
}

export interface DeleteCustomerArgs {
  customer_id: string;
}

export interface ListChargesArgs {
  customer?: string;
  limit?: number;
  starting_after?: string;
}

export interface GetChargeArgs {
  charge_id: string;
}

export interface CreateChargeArgs {
  amount?: string;
  currency?: string;
  customer?: string;
  source?: string;
  description?: string;
}

export interface RefundChargeArgs {
  charge_id?: string;
  amount?: string;
  reason?: string;
}

export interface ListRefundsArgs {
  charge?: string;
  limit?: number;
  starting_after?: string;
}

export interface CreatePaymentIntentArgs {
  amount?: string;
  currency?: string;
  customer?: string;
  description?: string;
  payment_method_types?: string[];
  payment_method?: string;
  capture_method?: string;
}

export interface GetPaymentIntentArgs {
  payment_intent_id: string;
}

export interface ListPaymentIntentsArgs {
  customer?: string;
  limit?: number;
  starting_after?: string;
}

export interface ConfirmPaymentIntentArgs {
  payment_intent_id: string;
  payment_method?: string;
  return_url?: string;
}

export interface CancelPaymentIntentArgs {
  payment_intent_id: string;
}

export interface CapturePaymentIntentArgs {
  payment_intent_id: string;
  amount_to_capture?: string;
}

export interface ListInvoicesArgs {
  customer?: string;
  limit?: number;
  starting_after?: string;
}

export interface GetInvoiceArgs {
  invoice_id: string;
}

export interface VoidInvoiceArgs {
  invoice_id: string;
}

export interface GetBalanceArgs {
}

export interface CreateSubscriptionArgs {
  customer?: string;
  price?: string;
  trial_days?: string;
}

export interface ListSubscriptionsArgs {
  customer?: string;
  status?: string;
  limit?: number;
  starting_after?: string;
}

export interface GetSubscriptionArgs {
  subscription_id: string;
}

export interface CreateProductArgs {
  name?: string;
  description?: string;
}

export interface ListProductsArgs {
  limit?: number;
  starting_after?: string;
}

export interface CreatePriceArgs {
  product?: string;
  unit_amount?: string;
  currency?: string;
  recurring_interval?: string;
}

export interface ListPricesArgs {
  product?: string;
  limit?: number;
  starting_after?: string;
}

export interface CreateCheckoutSessionArgs {
  mode?: string;
  success_url?: string;
  cancel_url?: string;
  line_items?: Array<Record<string, string>>;
}

export interface ListPaymentMethodsArgs {
  customer?: string;
  type?: string;
  limit?: number;
  starting_after?: string;
}

export interface ListDisputesArgs {
  limit?: number;
  starting_after?: string;
}

export interface GetDisputeArgs {
  dispute_id: string;
}

export interface CloseDisputeArgs {
  dispute_id: string;
}

export interface ListPayoutsArgs {
  limit?: number;
  starting_after?: string;
}

export interface CreatePayoutArgs {
  amount?: string;
  currency?: string;
}

export interface GetPayoutArgs {
  payout_id: string;
}

export interface ListEventsArgs {
  type?: string;
  limit?: number;
  starting_after?: string;
}

export interface GetEventArgs {
  event_id: string;
}

export interface CreateSetupIntentArgs {
  customer?: string;
  payment_method_types?: string[];
}

export interface GetSetupIntentArgs {
  setup_intent_id: string;
}

export class Stripe {
  credential: string;
  constructor(credential: string) { this.credential = credential; }
  /** GET /customers */
  async listCustomers(args: ListCustomersArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_customers", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /customers/{customer_id} */
  async getCustomer(args: GetCustomerArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_customer", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /customers */
  async createCustomer(args: CreateCustomerArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_customer", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /customers/{customer_id} */
  async updateCustomer(args: UpdateCustomerArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "update_customer", args as unknown as Record<string, unknown>, this.credential);
  }
  /** DELETE /customers/{customer_id} */
  async deleteCustomer(args: DeleteCustomerArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "delete_customer", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /charges */
  async listCharges(args: ListChargesArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_charges", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /charges/{charge_id} */
  async getCharge(args: GetChargeArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_charge", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /charges */
  async createCharge(args: CreateChargeArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_charge", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /refunds */
  async refundCharge(args: RefundChargeArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "refund_charge", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /refunds */
  async listRefunds(args: ListRefundsArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_refunds", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /payment_intents */
  async createPaymentIntent(args: CreatePaymentIntentArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_payment_intent", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /payment_intents/{payment_intent_id} */
  async getPaymentIntent(args: GetPaymentIntentArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_payment_intent", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /payment_intents */
  async listPaymentIntents(args: ListPaymentIntentsArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_payment_intents", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /payment_intents/{payment_intent_id}/confirm */
  async confirmPaymentIntent(args: ConfirmPaymentIntentArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "confirm_payment_intent", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /payment_intents/{payment_intent_id}/cancel */
  async cancelPaymentIntent(args: CancelPaymentIntentArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "cancel_payment_intent", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /payment_intents/{payment_intent_id}/capture */
  async capturePaymentIntent(args: CapturePaymentIntentArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "capture_payment_intent", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /invoices */
  async listInvoices(args: ListInvoicesArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_invoices", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /invoices/{invoice_id} */
  async getInvoice(args: GetInvoiceArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_invoice", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /invoices/{invoice_id}/void */
  async voidInvoice(args: VoidInvoiceArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "void_invoice", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /balance */
  async getBalance(args: GetBalanceArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_balance", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /subscriptions */
  async createSubscription(args: CreateSubscriptionArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_subscription", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /subscriptions */
  async listSubscriptions(args: ListSubscriptionsArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_subscriptions", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /subscriptions/{subscription_id} */
  async getSubscription(args: GetSubscriptionArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_subscription", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /products */
  async createProduct(args: CreateProductArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_product", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /products */
  async listProducts(args: ListProductsArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_products", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /prices */
  async createPrice(args: CreatePriceArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_price", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /prices */
  async listPrices(args: ListPricesArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_prices", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /checkout/sessions */
  async createCheckoutSession(args: CreateCheckoutSessionArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_checkout_session", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /payment_methods */
  async listPaymentMethods(args: ListPaymentMethodsArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_payment_methods", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /disputes */
  async listDisputes(args: ListDisputesArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_disputes", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /disputes/{dispute_id} */
  async getDispute(args: GetDisputeArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_dispute", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /disputes/{dispute_id}/close */
  async closeDispute(args: CloseDisputeArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "close_dispute", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /payouts */
  async listPayouts(args: ListPayoutsArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_payouts", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /payouts */
  async createPayout(args: CreatePayoutArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_payout", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /payouts/{payout_id} */
  async getPayout(args: GetPayoutArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_payout", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /events */
  async listEvents(args: ListEventsArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "list_events", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /events/{event_id} */
  async getEvent(args: GetEventArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_event", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /setup_intents */
  async createSetupIntent(args: CreateSetupIntentArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "create_setup_intent", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /setup_intents/{setup_intent_id} */
  async getSetupIntent(args: GetSetupIntentArgs): Promise<unknown> {
    return execute(STRIPE_BINDING, "get_setup_intent", args as unknown as Record<string, unknown>, this.credential);
  }
}
