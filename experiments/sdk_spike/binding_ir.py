"""Extended HTTP-binding IR — multi-language SDK de-risking spike.

SPIKE / EXPERIMENT. Touches nothing in ``src/``. It answers one make-or-break
question before committing to a multi-language SDK generator:

    Can the hand-written imperative request logic of the THREE HARDEST
    connectors (Airtable, Twilio, Shopify) be captured *declaratively* in a
    bounded vocabulary — or does it need open-ended imperative escape hatches,
    and for how much?

ToolsConnector's existing ``spec/`` IR stops at the *interface* (names, types,
JSON Schemas, danger flags, pagination strategy enum). It captures NONE of the
HTTP *binding* — method, path template, which arg goes to query vs path vs body,
serialization style (``fields[0]=``, ``sort[0][field]=``, ``records[]=``), body
wrapping/encoding, per-action base URL, response unwrap, pagination plumbing.
That binding currently lives only inside each connector's imperative ``_request``
and ``@action`` bodies (and ``runtime/serialization/`` is an empty placeholder).

The models below are the *missing binding layer*. They are deliberately a small,
finite vocabulary (Smithy-/OpenAPI-shaped) — config, not code.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Location(str, Enum):
    """Where a parameter is placed on the wire."""

    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    BODY = "body"


class Style(str, Enum):
    """How a (possibly list/object) parameter is serialized into the wire form.

    This is the crux of the "hard 20%". Every gnarly serialization across the
    three connectors reduces to one of these finite styles.
    """

    SIMPLE = "simple"                  # k=v
    INDEXED = "indexed"                # k[0]=a&k[1]=b            (Airtable fields[i])
    INDEXED_OBJECT = "indexed_object"  # k[0][sub]=v&k[1][sub]=v  (Airtable sort[i][field])
    BRACKET = "bracket"                # k[]=a&k[]=b              (Airtable records[] batch)
    FORM_EXPLODE = "form_explode"      # repeated k=a&k=b (no index)
    MAP = "map"                        # k[sub]=v per dict entry  (Stripe metadata[key]=value)


class ParamBinding(BaseModel):
    """Binding for a single action parameter (extends the interface ParameterSpec)."""

    name: str = Field(description="Python argument name.")
    wire: str = Field(description="Name on the wire (e.g. 'From', 'pageSize', 'page_info').")
    location: Location
    style: Style = Style.SIMPLE
    required: bool = False
    default: Any = None
    ty: Optional[str] = Field(
        default=None,
        description="Abstract type for codegen ('string'|'number'|'string[]'|'object'|'object[]'). "
        "The real generator derives this from the existing ParameterSpec JSON type; the spike "
        "infers scalars and sets the few non-inferable ones explicitly.",
    )

    # INDEXED_OBJECT: ordered sub-keys emitted per element + per-subkey defaults.
    subkeys: list[str] = Field(default_factory=list)
    subkey_defaults: dict[str, Any] = Field(default_factory=dict)

    # BODY placement.
    body_key: Optional[str] = Field(
        default=None, description="Key inside the JSON body (defaults to `wire`)."
    )
    item_wrap: Optional[str] = Field(
        default=None,
        description="Wrap each list element under this key, e.g. records -> [{'fields': elem}].",
    )

    # Bounded transforms (clamps that today are hand-coded as min(x, N)/x[:N]).
    max: Optional[int] = Field(default=None, description="Clamp an int value to <= max.")
    max_items: Optional[int] = Field(default=None, description="Send only the first N list items.")


class PaginationKind(str, Enum):
    NONE = "none"
    OFFSET_TOKEN = "offset_token"  # cursor in a body field -> re-injected as a query param
    LINK_HEADER = "link_header"    # parse Link rel=next, extract page_info -> query param
    FOLLOW_URL = "follow_url"      # a body field IS the next request URL; GET it directly
    LAST_ID = "last_id"            # cursor = items[-1][id_field], guarded by has_more (Stripe)


class PaginationBinding(BaseModel):
    kind: PaginationKind = PaginationKind.NONE
    items_field: Optional[str] = Field(default=None, description="Response field holding the page.")
    token_field: Optional[str] = Field(
        default=None,
        description="Body field holding the next cursor (OFFSET_TOKEN) or next URL (FOLLOW_URL).",
    )
    token_param_py: Optional[str] = Field(
        default=None,
        description="Python arg name the cursor is fed into on the next call (OFFSET_TOKEN/LINK_HEADER/LAST_ID).",
    )
    link_rel: str = "next"
    # LAST_ID: the cursor is the id of the last element of items_field, sent only
    # while has_more_field is truthy (Stripe: data[-1].id, has_more).
    id_field: str = "id"
    has_more_field: str = "has_more"
    carry: Optional[list[str]] = Field(
        default=None,
        description="Python arg names carried to the next page. None = carry ALL previous args.",
    )


class AuthKind(str, Enum):
    BEARER = "bearer"            # Authorization: Bearer <cred>
    HEADER_KEY = "header_key"    # <header>: <cred>
    BASIC_SPLIT = "basic_split"  # cred 'user:pass' -> Authorization: Basic base64(cred)
    BASIC_USER = "basic_user"    # Authorization: Basic base64(cred + ':')  — key as username,
    #                              empty password (Stripe, many key-auth REST APIs)


class EndpointBinding(BaseModel):
    """A base URL + auth + default encoding. Connectors may have several
    (Airtable data vs meta; Twilio main/verify/lookup/conversations)."""

    id: str
    base_url: str = Field(description="Base URL; may contain {ctx} templates e.g. {store}.")
    encoding: str = Field(default="json", description="Default body encoding: 'json' or 'form'.")
    auth_kind: AuthKind = AuthKind.BEARER
    auth_header: str = "Authorization"
    auth_cred_ctx: Optional[str] = Field(
        default=None,
        description="If set, use ctx[this] as the auth credential instead of the raw credential.",
    )
    extra_headers: dict[str, str] = Field(default_factory=dict)


class ActionBinding(BaseModel):
    name: str
    method: str
    endpoint: str = Field(description="Endpoint id this action targets.")
    path: str = Field(description="Path template with {ctx} and {path-param} placeholders.")
    params: list[ParamBinding] = Field(default_factory=list)
    body_wrap: Optional[str] = Field(
        default=None, description="Wrap the whole JSON body under one key (Shopify 'product')."
    )
    body_encoding: Optional[str] = Field(default=None, description="Override endpoint encoding.")
    unwrap: Optional[str] = Field(default=None, description="Dotted path to extract the result.")
    pagination: PaginationBinding = Field(default_factory=PaginationBinding)


class ContextVar(BaseModel):
    """A connector-level value derived from the credential, usable in templates."""

    name: str
    source: str = Field(
        default="whole",
        description="'whole' = entire credential; 'split:<i>:<sep>' = credential.split(sep)[i].",
    )


class ConnectorBinding(BaseModel):
    name: str
    endpoints: dict[str, EndpointBinding]
    default_endpoint: str
    ctx_vars: list[ContextVar] = Field(default_factory=list)
    actions: dict[str, ActionBinding] = Field(default_factory=dict)
    escape_hatches: list[str] = Field(
        default_factory=list,
        description="Action names that resist declarative binding (e.g. method varies by "
        "arg value) — generated as typed methods delegating to a per-language override, so "
        "the SDK surface stays complete. The honest <2.7% (e.g. stripe.cancel_subscription).",
    )
