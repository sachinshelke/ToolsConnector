// AUTO-GENERATED from the connector binding. Do not edit by hand.
import { execute } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";

export const TWILIO_BINDING: ConnectorB = {
  "name": "twilio",
  "endpoints": {
    "main": {
      "id": "main",
      "baseUrl": "https://api.twilio.com/2010-04-01",
      "encoding": "form",
      "authKind": "basic_split",
      "authHeader": "Authorization"
    },
    "verify": {
      "id": "verify",
      "baseUrl": "https://verify.twilio.com/v2",
      "encoding": "form",
      "authKind": "basic_split",
      "authHeader": "Authorization"
    }
  },
  "defaultEndpoint": "main",
  "actions": {
    "send_sms": {
      "name": "send_sms",
      "method": "POST",
      "endpoint": "main",
      "path": "/Accounts/{account_sid}/Messages.json",
      "params": [
        {
          "name": "to",
          "wire": "To",
          "location": "body"
        },
        {
          "name": "from_",
          "wire": "From",
          "location": "body"
        },
        {
          "name": "body",
          "wire": "Body",
          "location": "body"
        }
      ]
    },
    "list_messages": {
      "name": "list_messages",
      "method": "GET",
      "endpoint": "main",
      "path": "/Accounts/{account_sid}/Messages.json",
      "params": [
        {
          "name": "to",
          "wire": "To",
          "location": "query"
        },
        {
          "name": "from_",
          "wire": "From",
          "location": "query"
        },
        {
          "name": "limit",
          "wire": "PageSize",
          "location": "query",
          "default": 20,
          "max": 1000
        }
      ],
      "unwrap": "messages",
      "pagination": {
        "kind": "follow_url",
        "itemsField": "messages",
        "tokenField": "next_page_uri"
      }
    },
    "create_verify_service": {
      "name": "create_verify_service",
      "method": "POST",
      "endpoint": "verify",
      "path": "/Services",
      "params": [
        {
          "name": "friendly_name",
          "wire": "FriendlyName",
          "location": "body"
        }
      ]
    }
  },
  "ctxVars": [
    {
      "name": "account_sid",
      "source": "split:0::"
    }
  ]
};

export interface SendSmsArgs {
  to?: string;
  from_?: string;
  body?: string;
}

export interface ListMessagesArgs {
  to?: string;
  from_?: string;
  limit?: number;
}

export interface CreateVerifyServiceArgs {
  friendly_name?: string;
}

export class Twilio {
  credential: string;
  constructor(credential: string) { this.credential = credential; }
  /** POST /Accounts/{account_sid}/Messages.json */
  async sendSms(args: SendSmsArgs): Promise<unknown> {
    return execute(TWILIO_BINDING, "send_sms", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /Accounts/{account_sid}/Messages.json */
  async listMessages(args: ListMessagesArgs): Promise<unknown> {
    return execute(TWILIO_BINDING, "list_messages", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /Services */
  async createVerifyService(args: CreateVerifyServiceArgs): Promise<unknown> {
    return execute(TWILIO_BINDING, "create_verify_service", args as unknown as Record<string, unknown>, this.credential);
  }
}
