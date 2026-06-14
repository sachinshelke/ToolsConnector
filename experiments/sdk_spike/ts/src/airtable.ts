// AUTO-GENERATED from the connector binding. Do not edit by hand.
import { execute } from "./runtime.ts";
import type { ConnectorB } from "./runtime.ts";

export const AIRTABLE_BINDING: ConnectorB = {
  "name": "airtable",
  "endpoints": {
    "data": {
      "id": "data",
      "baseUrl": "https://api.airtable.com/v0",
      "encoding": "json",
      "authKind": "bearer",
      "authHeader": "Authorization"
    },
    "meta": {
      "id": "meta",
      "baseUrl": "https://api.airtable.com/v0/meta",
      "encoding": "json",
      "authKind": "bearer",
      "authHeader": "Authorization"
    }
  },
  "defaultEndpoint": "data",
  "actions": {
    "list_records": {
      "name": "list_records",
      "method": "GET",
      "endpoint": "data",
      "path": "/{base_id}/{table_name}",
      "params": [
        {
          "name": "base_id",
          "wire": "base_id",
          "location": "path"
        },
        {
          "name": "table_name",
          "wire": "table_name",
          "location": "path"
        },
        {
          "name": "limit",
          "wire": "pageSize",
          "location": "query",
          "default": 100,
          "max": 100
        },
        {
          "name": "fields",
          "wire": "fields",
          "location": "query",
          "style": "indexed"
        },
        {
          "name": "filter_formula",
          "wire": "filterByFormula",
          "location": "query"
        },
        {
          "name": "sort",
          "wire": "sort",
          "location": "query",
          "style": "indexed_object",
          "subkeys": [
            "field",
            "direction"
          ],
          "subkeyDefaults": {
            "field": "",
            "direction": "asc"
          }
        },
        {
          "name": "offset",
          "wire": "offset",
          "location": "query"
        }
      ],
      "unwrap": "records",
      "pagination": {
        "kind": "offset_token",
        "itemsField": "records",
        "tokenField": "offset",
        "tokenParamPy": "offset"
      }
    },
    "delete_records": {
      "name": "delete_records",
      "method": "DELETE",
      "endpoint": "data",
      "path": "/{base_id}/{table_name}",
      "params": [
        {
          "name": "base_id",
          "wire": "base_id",
          "location": "path"
        },
        {
          "name": "table_name",
          "wire": "table_name",
          "location": "path"
        },
        {
          "name": "record_ids",
          "wire": "records",
          "location": "query",
          "style": "bracket",
          "maxItems": 10
        }
      ]
    },
    "create_record": {
      "name": "create_record",
      "method": "POST",
      "endpoint": "data",
      "path": "/{base_id}/{table_name}",
      "params": [
        {
          "name": "base_id",
          "wire": "base_id",
          "location": "path"
        },
        {
          "name": "table_name",
          "wire": "table_name",
          "location": "path"
        },
        {
          "name": "fields",
          "wire": "fields",
          "location": "body",
          "bodyKey": "fields"
        }
      ]
    },
    "batch_create": {
      "name": "batch_create",
      "method": "POST",
      "endpoint": "data",
      "path": "/{base_id}/{table_name}",
      "params": [
        {
          "name": "base_id",
          "wire": "base_id",
          "location": "path"
        },
        {
          "name": "table_name",
          "wire": "table_name",
          "location": "path"
        },
        {
          "name": "records",
          "wire": "records",
          "location": "body",
          "bodyKey": "records",
          "itemWrap": "fields",
          "maxItems": 10
        }
      ]
    },
    "get_base_schema": {
      "name": "get_base_schema",
      "method": "GET",
      "endpoint": "meta",
      "path": "/bases/{base_id}/tables",
      "params": [
        {
          "name": "base_id",
          "wire": "base_id",
          "location": "path"
        }
      ],
      "unwrap": "tables"
    }
  }
};

export interface ListRecordsArgs {
  base_id: string;
  table_name: string;
  limit?: number;
  fields?: string[];
  filter_formula?: string;
  sort?: Array<Record<string, string>>;
  offset?: string;
}

export interface DeleteRecordsArgs {
  base_id: string;
  table_name: string;
  record_ids?: string[];
}

export interface CreateRecordArgs {
  base_id: string;
  table_name: string;
  fields?: Record<string, unknown>;
}

export interface BatchCreateArgs {
  base_id: string;
  table_name: string;
  records?: Array<Record<string, unknown>>;
}

export interface GetBaseSchemaArgs {
  base_id: string;
}

export class Airtable {
  credential: string;
  overrides: Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>>;
  constructor(credential: string, opts?: { overrides?: Record<string, (cred: string, args: Record<string, unknown>) => Promise<unknown>> }) { this.credential = credential; this.overrides = opts?.overrides ?? {}; }
  /** GET /{base_id}/{table_name} */
  async listRecords(args: ListRecordsArgs): Promise<unknown> {
    return execute(AIRTABLE_BINDING, "list_records", args as unknown as Record<string, unknown>, this.credential);
  }
  /** DELETE /{base_id}/{table_name} */
  async deleteRecords(args: DeleteRecordsArgs): Promise<unknown> {
    return execute(AIRTABLE_BINDING, "delete_records", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /{base_id}/{table_name} */
  async createRecord(args: CreateRecordArgs): Promise<unknown> {
    return execute(AIRTABLE_BINDING, "create_record", args as unknown as Record<string, unknown>, this.credential);
  }
  /** POST /{base_id}/{table_name} */
  async batchCreate(args: BatchCreateArgs): Promise<unknown> {
    return execute(AIRTABLE_BINDING, "batch_create", args as unknown as Record<string, unknown>, this.credential);
  }
  /** GET /bases/{base_id}/tables */
  async getBaseSchema(args: GetBaseSchemaArgs): Promise<unknown> {
    return execute(AIRTABLE_BINDING, "get_base_schema", args as unknown as Record<string, unknown>, this.credential);
  }
}
