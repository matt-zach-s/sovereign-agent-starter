import httpx
from integrations.models import Integration, Operation, Auth
from integrations.dispatch import dispatch


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")


def test_path_substitution_and_auth_header():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"id": "42", "name": "Widget"})

    integ = Integration(name="Inv", base_url="http://inv.internal/v1",
                        auth=Auth(type="bearer", secret_ref="t"))
    op = Operation(operation_id="getItem", method="get", path="/items/{id}")
    out = dispatch(integ, op, {"id": "42"}, "tok-9", client=_client(handler))
    assert "Widget" in out
    assert seen["url"] == "http://inv.internal/v1/items/42"
    assert seen["auth"] == "Bearer tok-9"


def test_api_key_header_and_query_params():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, text="ok")

    integ = Integration(name="Inv", base_url="http://inv/v1",
                        auth=Auth(type="api_key_header", header="X-API-Key", secret_ref="k"))
    op = Operation(operation_id="getItems", method="get", path="/items")
    dispatch(integ, op, {"limit": 5}, "abc", client=_client(handler))
    assert seen["key"] == "abc"
    assert "limit=5" in seen["url"]


def test_post_sends_json_body():
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(201, text="created")

    integ = Integration(name="Inv", base_url="http://inv/v1", auth=Auth())
    op = Operation(operation_id="reserve", method="post", path="/items/{id}/reserve")
    out = dispatch(integ, op, {"id": "7", "qty": 3}, None, client=_client(handler))
    assert "created" in out
    assert '"qty": 3' in seen["body"] and "id" not in seen["body"]  # id went to path


def test_errors_are_returned_not_raised():
    def handler(request):
        raise httpx.ConnectError("refused")

    integ = Integration(name="Inv", base_url="http://inv/v1", auth=Auth())
    op = Operation(operation_id="x", method="get", path="/x")
    out = dispatch(integ, op, {}, None, client=_client(handler))
    assert out.startswith("tool error")
