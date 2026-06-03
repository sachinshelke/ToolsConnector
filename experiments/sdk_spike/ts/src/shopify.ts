// AUTO-GENERATED from the connector binding. Do not edit by hand.
import { execute } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";

export const SHOPIFY_BINDING: ConnectorB = {
  "name": "shopify",
  "endpoints": {
    "main": {
      "id": "main",
      "baseUrl": "https://{store}.myshopify.com/admin/api/2024-01",
      "encoding": "json",
      "authKind": "header_key",
      "authHeader": "X-Shopify-Access-Token",
      "authCredCtx": "access_token",
      "extraHeaders": {
        "Accept": "application/json"
      }
    }
  },
  "defaultEndpoint": "main",
  "actions": {
    "list_products": {
      "name": "list_products",
      "method": "GET",
      "endpoint": "main",
      "path": "/products.json",
      "params": [
        {
          "name": "limit",
          "wire": "limit",
          "location": "query",
          "default": 50,
          "max": 250
        },
        {
          "name": "since_id",
          "wire": "since_id",
          "location": "query"
        },
        {
          "name": "page_info",
          "wire": "page_info",
          "location": "query"
        }
      ],
      "unwrap": "products",
      "pagination": {
        "kind": "link_header",
        "itemsField": "products",
        "tokenParamPy": "page_info",
        "carry": [
          "limit"
        ]
      }
    },
    "create_product": {
      "name": "create_product",
      "method": "PUT",
      "endpoint": "main",
      "path": "/products.json",
      "params": [
        {
          "name": "title",
          "wire": "title",
          "location": "body"
        },
        {
          "name": "body_html",
          "wire": "body_html",
          "location": "body"
        },
        {
          "name": "vendor",
          "wire": "vendor",
          "location": "body"
        },
        {
          "name": "product_type",
          "wire": "product_type",
          "location": "body"
        },
        {
          "name": "variants",
          "wire": "variants",
          "location": "body"
        }
      ],
      "bodyWrap": "product"
    }
  },
  "ctxVars": [
    {
      "name": "access_token",
      "source": "split:0::"
    },
    {
      "name": "store",
      "source": "split:1::"
    }
  ]
};

export interface ListProductsArgs {
  limit?: number;
  since_id?: string;
  page_info?: string;
}

export interface CreateProductArgs {
  title?: string;
  body_html?: string;
  vendor?: string;
  product_type?: string;
  variants?: Array<Record<string, unknown>>;
}

export class Shopify {
  credential: string;
  constructor(credential: string) { this.credential = credential; }
  /** GET /products.json */
  async listProducts(args: ListProductsArgs): Promise<unknown> {
    return execute(SHOPIFY_BINDING, "list_products", args as unknown as Record<string, unknown>, this.credential);
  }
  /** PUT /products.json */
  async createProduct(args: CreateProductArgs): Promise<unknown> {
    return execute(SHOPIFY_BINDING, "create_product", args as unknown as Record<string, unknown>, this.credential);
  }
}
