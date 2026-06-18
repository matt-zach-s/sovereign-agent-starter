import json
from integrations.models import Integration, Operation, Auth
from integrations.openapi_tools import parse_spec, operation_to_tool, tools_for

SPEC = json.dumps({
    "openapi": "3.0.0",
    "info": {"title": "Inventory API", "version": "1"},
    "servers": [{"url": "http://inv.internal/v1"}],
    "paths": {
        "/items": {"get": {"operationId": "getItems", "summary": "List items"}},
        "/items/{id}": {
            "get": {
                "operationId": "getItem", "summary": "Get one",
                "parameters": [{"name": "id", "in": "path", "required": True,
                                "schema": {"type": "string"}}],
            },
            "delete": {"summary": "Delete"},  # no operationId -> derived name
        },
    },
})


def test_parse_spec_lists_operations_and_title():
    spec = parse_spec(SPEC)
    assert spec.title == "Inventory API"
    assert spec.server == "http://inv.internal/v1"
    ids = {o.operation_id for o in spec.operations}
    assert "getItems" in ids and "getItem" in ids
    # operationId-less op gets a derived, stable name
    assert any(o.method == "delete" and o.path == "/items/{id}" for o in spec.operations)


def test_get_item_tool_has_path_param():
    spec = parse_spec(SPEC)
    op = next(o for o in spec.operations if o.operation_id == "getItem")
    tool = operation_to_tool(op)
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "getItem"
    assert "id" in tool["function"]["parameters"]["properties"]
    assert tool["function"]["parameters"]["required"] == ["id"]


def test_tools_for_only_includes_integration_operations():
    op = Operation(operation_id="getItems", method="get", path="/items")
    integ = Integration(name="Inv", base_url="http://x", operations=[op])
    tools = tools_for(integ)
    assert len(tools) == 1 and tools[0]["function"]["name"] == "getItems"


def test_parse_spec_rejects_garbage():
    try:
        parse_spec("not a spec at all: [")
        assert False, "expected ValueError"
    except ValueError:
        pass
