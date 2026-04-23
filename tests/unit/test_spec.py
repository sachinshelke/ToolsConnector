"""Unit tests for the spec/ module."""

from __future__ import annotations

import json

from toolsconnector.spec import (
    SPEC_VERSION,
    ActionSpec,
    AuthType,
    ConnectorCategory,
    ConnectorSpec,
    ErrorCode,
    OAuthSpec,
    PaginationStrategyType,
    ParameterSpec,
    ProtocolType,
    RateLimitSpec,
    ScopeSet,
)


class TestSpecVersion:
    def test_spec_version_is_string(self):
        assert isinstance(SPEC_VERSION, str)
        assert SPEC_VERSION == "1.0"


class TestConnectorCategory:
    def test_all_categories_exist(self):
        assert ConnectorCategory.COMMUNICATION == "communication"
        assert ConnectorCategory.CRM == "crm"
        assert ConnectorCategory.DATABASE == "database"
        assert ConnectorCategory.CUSTOM == "custom"

    def test_category_count(self):
        assert len(ConnectorCategory) >= 15


class TestProtocolType:
    def test_protocol_types(self):
        assert ProtocolType.REST == "rest"
        assert ProtocolType.GRAPHQL == "graphql"
        assert ProtocolType.SOAP == "soap"
        assert ProtocolType.GRPC == "grpc"
        assert ProtocolType.WEBSOCKET == "websocket"


class TestAuthType:
    def test_all_auth_types(self):
        assert AuthType.API_KEY == "api_key"
        assert AuthType.OAUTH2 == "oauth2"
        assert AuthType.OAUTH2_PKCE == "oauth2_pkce"
        assert AuthType.HMAC == "hmac"
        assert AuthType.AWS_SIGV4 == "aws_sigv4"
        assert AuthType.MTLS == "mtls"

    def test_auth_type_count(self):
        assert len(AuthType) >= 10


class TestErrorCode:
    def test_error_codes_exist(self):
        assert ErrorCode.AUTH_TOKEN_EXPIRED == "AUTH_TOKEN_EXPIRED"
        assert ErrorCode.API_RATE_LIMITED == "API_RATE_LIMITED"
        assert ErrorCode.TRANSPORT_TIMEOUT == "TRANSPORT_TIMEOUT"
        assert ErrorCode.CONNECTOR_NOT_CONFIGURED == "CONNECTOR_NOT_CONFIGURED"
        assert ErrorCode.CONFIG_INVALID == "CONFIG_INVALID"

    def test_error_code_count(self):
        assert len(ErrorCode) >= 20


class TestPaginationStrategyType:
    def test_strategies(self):
        assert PaginationStrategyType.CURSOR == "cursor"
        assert PaginationStrategyType.TOKEN == "token"
        assert PaginationStrategyType.OFFSET == "offset"
        assert PaginationStrategyType.KEYSET == "keyset"
        assert PaginationStrategyType.NONE == "none"


class TestParameterSpec:
    def test_create_parameter(self):
        ps = ParameterSpec(
            name="query",
            type="string",
            description="Search query",
            required=True,
        )
        assert ps.name == "query"
        assert ps.type == "string"
        assert ps.required is True

    def test_optional_parameter(self):
        ps = ParameterSpec(
            name="limit",
            type="integer",
            description="Max results",
            required=False,
            default=10,
        )
        assert ps.required is False
        assert ps.default == 10


class TestActionSpec:
    def test_create_action_spec(self):
        spec = ActionSpec(
            name="list_emails",
            description="List emails",
            parameters=[
                ParameterSpec(name="query", type="string", description="Search"),
            ],
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        assert spec.name == "list_emails"
        assert len(spec.parameters) == 1
        assert spec.dangerous is False
        assert spec.idempotent is False

    def test_dangerous_action(self):
        spec = ActionSpec(
            name="delete_email",
            description="Delete an email",
            dangerous=True,
        )
        assert spec.dangerous is True


class TestOAuthSpec:
    def test_oauth_config(self):
        oauth = OAuthSpec(
            auth_url="https://accounts.google.com/o/oauth2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=[
                ScopeSet(name="read", scopes=["gmail.readonly"]),
                ScopeSet(name="send", scopes=["gmail.send"]),
            ],
        )
        assert len(oauth.scopes) == 2
        assert oauth.scopes[0].name == "read"


class TestConnectorSpec:
    def test_create_connector_spec(self):
        spec = ConnectorSpec(
            name="gmail",
            display_name="Gmail",
            category=ConnectorCategory.COMMUNICATION,
            description="Gmail connector",
            protocol=ProtocolType.REST,
            base_url="https://gmail.googleapis.com",
        )
        assert spec.name == "gmail"
        assert spec.spec_version == SPEC_VERSION
        assert spec.protocol == ProtocolType.REST

    def test_json_schema_generation(self):
        schema = ConnectorSpec.model_json_schema()
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "actions" in schema["properties"]

    def test_connector_spec_serialization(self):
        spec = ConnectorSpec(
            name="test",
            display_name="Test",
            category=ConnectorCategory.CUSTOM,
            description="Test connector",
        )
        d = spec.model_dump()
        assert isinstance(d, dict)
        assert d["name"] == "test"

        j = spec.model_dump_json()
        parsed = json.loads(j)
        assert parsed["name"] == "test"


class TestRateLimitSpec:
    def test_default_rate_limit(self):
        rl = RateLimitSpec()
        assert rl.rate == 60
        assert rl.period == 60
        assert rl.burst == 10

    def test_custom_rate_limit(self):
        rl = RateLimitSpec(rate=250, period=60, burst=50)
        assert rl.rate == 250
