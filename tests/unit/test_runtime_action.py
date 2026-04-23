"""Unit tests for the @action decorator and BaseConnector."""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType
from toolsconnector.types import PageState, PaginatedList


class TestItem(BaseModel):
    id: str
    value: int


class SampleConnector(BaseConnector):
    """A test connector for unit testing."""

    name = "sample"
    display_name = "Sample"
    category = ConnectorCategory.CUSTOM
    description = "A sample connector for testing."
    protocol = ProtocolType.REST

    @action("List items with optional filtering")
    async def list_items(
        self,
        query: str = "",
        limit: int = 10,
        tags: Optional[list[str]] = None,
    ) -> PaginatedList[TestItem]:
        """List all items.

        Args:
            query: Filter query string.
            limit: Maximum items to return.
            tags: Optional tags to filter by.

        Returns:
            Paginated list of items.
        """
        items = [TestItem(id="1", value=42)]
        return PaginatedList(items=items, page_state=PageState())

    @action("Get a single item by ID")
    async def get_item(self, item_id: str) -> TestItem:
        """Get one item.

        Args:
            item_id: The item identifier.

        Returns:
            The requested item.
        """
        return TestItem(id=item_id, value=0)

    @action("Delete an item", dangerous=True, requires_scope="admin")
    async def delete_item(self, item_id: str) -> None:
        """Delete an item permanently.

        Args:
            item_id: The item to delete.
        """
        pass


class TestActionDecorator:
    def test_action_meta_attached(self):
        meta = SampleConnector.list_items.__action_meta__
        assert meta.name == "list_items"
        assert meta.description == "List items with optional filtering"

    def test_parameter_extraction(self):
        meta = SampleConnector.list_items.__action_meta__
        param_names = [p.name for p in meta.parameters]
        assert "query" in param_names
        assert "limit" in param_names
        assert "tags" in param_names

    def test_parameter_types(self):
        meta = SampleConnector.list_items.__action_meta__
        params = {p.name: p for p in meta.parameters}
        assert params["query"].type == "string"
        assert params["limit"].type == "integer"

    def test_parameter_defaults(self):
        meta = SampleConnector.list_items.__action_meta__
        params = {p.name: p for p in meta.parameters}
        assert params["query"].default == ""
        assert params["limit"].default == 10
        assert params["query"].required is False
        assert params["limit"].required is False

    def test_required_parameter(self):
        meta = SampleConnector.get_item.__action_meta__
        params = {p.name: p for p in meta.parameters}
        assert params["item_id"].required is True

    def test_dangerous_flag(self):
        meta = SampleConnector.delete_item.__action_meta__
        assert meta.dangerous is True

    def test_requires_scope(self):
        meta = SampleConnector.delete_item.__action_meta__
        assert meta.requires_scope == "admin"

    def test_input_schema_generated(self):
        meta = SampleConnector.list_items.__action_meta__
        schema = meta.input_schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "query" in schema["properties"]
        assert "limit" in schema["properties"]

    def test_docstring_descriptions(self):
        meta = SampleConnector.list_items.__action_meta__
        params = {p.name: p for p in meta.parameters}
        assert "Filter" in params["query"].description
        assert "Maximum" in params["limit"].description


class TestBaseConnector:
    def test_get_actions(self):
        actions = SampleConnector.get_actions()
        assert "list_items" in actions
        assert "get_item" in actions
        assert "delete_item" in actions

    def test_get_spec(self):
        spec = SampleConnector.get_spec()
        assert spec.name == "sample"
        assert spec.display_name == "Sample"
        assert spec.category == ConnectorCategory.CUSTOM
        assert "list_items" in spec.actions
        assert "get_item" in spec.actions
        assert "delete_item" in spec.actions

    def test_spec_action_details(self):
        spec = SampleConnector.get_spec()
        list_action = spec.actions["list_items"]
        assert list_action.description == "List items with optional filtering"
        assert len(list_action.parameters) == 3

    def test_sync_wrapper(self):
        conn = SampleConnector()
        result = conn.list_items(limit=5)
        assert isinstance(result, PaginatedList)
        assert len(result.items) == 1

    def test_sync_wrapper_get(self):
        conn = SampleConnector()
        result = conn.get_item(item_id="test-123")
        assert result.id == "test-123"

    def test_repr(self):
        conn = SampleConnector()
        r = repr(conn)
        assert "Sample" in r or "sample" in r

    def test_repr_with_tenant(self):
        conn = SampleConnector(tenant_id="user-1")
        r = repr(conn)
        assert "user-1" in r


class TestActionMustBeAsync:
    def test_sync_action_raises(self):
        with pytest.raises(TypeError, match="must be async"):

            class BadConnector(BaseConnector):
                name = "bad"

                @action("This should fail")
                def sync_method(self, x: int) -> int:
                    return x
