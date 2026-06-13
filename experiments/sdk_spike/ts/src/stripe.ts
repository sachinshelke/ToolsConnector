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
}
