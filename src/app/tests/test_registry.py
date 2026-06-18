from integrations.models import Integration, Operation, Auth
from integrations.registry import Registry


def _integ(name="Inv", enabled=True, source="config"):
    op = Operation(operation_id="getItems", method="get", path="/items")
    return Integration(name=name, base_url="http://x", enabled=enabled,
                       operations=[op], source=source)


def test_tools_only_for_enabled():
    reg = Registry([_integ(enabled=True), _integ(name="Off", enabled=False)], None)
    names = [t["function"]["name"] for t in reg.tools()]
    assert names == ["getItems"]  # only the enabled one


def test_set_enabled_toggles_tools():
    reg = Registry([_integ()], None)
    assert reg.set_enabled("inv", False) is True
    assert reg.tools() == []
    assert reg.set_enabled("nope", True) is False


def test_add_session_stores_secret_in_memory():
    reg = Registry([], None)
    integ = Integration(name="Tickets", base_url="http://t",
                        auth=Auth(type="bearer", secret_ref="tickets-token"),
                        operations=[Operation("list", "get", "/t")])
    reg.add_session(integ, "tok-123")
    assert reg.get("tickets").source == "session"
    assert reg.secret_for(reg.get("tickets")) == "tok-123"


def test_remove_session_only():
    reg = Registry([_integ(source="config")], None)
    assert reg.remove("inv") is False          # config-sourced: protected
    s = Integration(name="S", base_url="http://x",
                    operations=[Operation("o", "get", "/")], source="session")
    reg.add_session(s, None)
    assert reg.remove("s") is True


def test_tool_index_maps_name_to_op():
    reg = Registry([_integ()], None)
    idx = reg.tool_index()
    integ, op = idx["getItems"]
    assert op.path == "/items" and integ.id == "inv"
