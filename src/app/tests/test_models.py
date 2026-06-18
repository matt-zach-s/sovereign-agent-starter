from integrations.models import (
    Auth, Operation, Integration, ParsedSpec, slugify, sanitize_tool_name,
)


def test_slugify_and_tool_name():
    assert slugify("Inventory API") == "inventory-api"
    assert sanitize_tool_name("get/items {weird}") == "get_items_weird"


def test_auth_roundtrip_drops_empty():
    a = Auth.from_dict({"type": "api_key_header", "header": "X-API-Key",
                        "secret_ref": "inventory-api-key"})
    assert a.to_dict() == {"type": "api_key_header", "header": "X-API-Key",
                           "secret_ref": "inventory-api-key"}
    assert Auth.from_dict(None).to_dict() == {"type": "none"}


def test_integration_def_dict_uses_full_operations():
    op = Operation(operation_id="getItem", method="get", path="/items/{id}",
                   summary="Get one", parameters={"type": "object", "properties": {}})
    integ = Integration(name="Inventory API", base_url="http://inv.internal/v1",
                        operations=[op], auth=Auth(type="bearer", secret_ref="inv-token"))
    d = integ.to_def_dict()
    assert d["name"] == "Inventory API"
    assert d["id"] == "inventory-api"
    assert d["operations"][0]["operation_id"] == "getItem"
    assert d["auth"] == {"type": "bearer", "secret_ref": "inv-token"}
    # round-trips back
    assert Integration.from_dict(d).operations[0].path == "/items/{id}"
