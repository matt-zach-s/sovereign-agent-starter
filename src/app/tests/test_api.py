import json
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integrations.registry import Registry
from integrations.api import build_router

SPEC = json.dumps({
    "openapi": "3.0.0", "info": {"title": "Inventory API"},
    "servers": [{"url": "http://inv.internal/v1"}],
    "paths": {"/items": {"get": {"operationId": "getItems", "summary": "List"}}},
})


def _app(registry):
    app = FastAPI()
    # http_client_factory returns a client that serves SPEC for any GET (parse via URL)
    def factory(*a, **k):
        def handler(request):
            return httpx.Response(200, text=SPEC)
        return httpx.Client(transport=httpx.MockTransport(handler))
    app.include_router(build_router(registry, http_client_factory=factory))
    return app


def test_parse_then_create_lists_and_returns_manifest():
    reg = Registry([], None)
    client = TestClient(_app(reg))

    parsed = client.post("/api/integrations/parse",
                         json={"spec_url": "http://inv.internal/v1/openapi.json"})
    assert parsed.status_code == 200
    assert parsed.json()["title"] == "Inventory API"
    assert parsed.json()["operations"][0]["operation_id"] == "getItems"

    created = client.post("/api/integrations", json={
        "name": "Inventory API", "base_url": "http://inv.internal/v1",
        "auth": {"type": "bearer", "secret_ref": "inv-token"},
        "secret_value": "tok-1",
        "operations": [{"operation_id": "getItems", "method": "get", "path": "/items"}],
    })
    assert created.status_code == 200
    body = created.json()
    assert "ConfigMap" in body["manifest"]["configmap_yaml"]
    assert "tok-1" in body["manifest"]["secret_yaml"]

    listing = client.get("/api/integrations").json()
    assert listing[0]["name"] == "Inventory API"
    assert listing[0]["tool_count"] == 1
    assert listing[0]["source"] == "session"
    # secret value must never appear in a GET response
    assert "tok-1" not in client.get("/api/integrations").text


def test_toggle_and_delete():
    reg = Registry([], None)
    client = TestClient(_app(reg))
    client.post("/api/integrations", json={
        "name": "T", "base_url": "http://t", "auth": {"type": "none"},
        "operations": [{"operation_id": "o", "method": "get", "path": "/o"}]})
    assert client.patch("/api/integrations/t", json={"enabled": False}).status_code == 200
    assert reg.get("t").enabled is False
    assert client.delete("/api/integrations/t").status_code == 200
    assert reg.get("t") is None


def test_parse_bad_spec_returns_400():
    reg = Registry([], None)
    client = TestClient(_app(reg))
    r = client.post("/api/integrations/parse", json={"spec_text": "garbage: ["})
    assert r.status_code == 400


def _mcp_factory():
    """A factory returning an httpx client over a one-tool MCP MockTransport."""
    def handler(request):
        p = json.loads(request.read())
        if p.get("id") is None:
            return httpx.Response(202, text="")
        m = p["method"]
        if m == "initialize":
            res = {"protocolVersion": "2025-06-18"}
        elif m == "tools/list":
            res = {"tools": [{"name": "ping", "description": "Ping",
                              "inputSchema": {"type": "object", "properties": {}}}]}
        else:
            res = {}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": p["id"], "result": res})
    return lambda *a, **k: httpx.Client(transport=httpx.MockTransport(handler))


def test_mcp_discover_then_create_lists_tools():
    reg = Registry([], None)
    app = FastAPI()
    app.include_router(build_router(reg, mcp_client_factory=_mcp_factory()))
    client = TestClient(app)

    disc = client.post("/api/integrations/mcp/discover",
                       json={"server_url": "http://mcp.internal/rpc"})
    assert disc.status_code == 200
    tools = disc.json()["tools"]
    assert tools[0]["name"] == "ping"

    created = client.post("/api/integrations", json={
        "name": "Tickets MCP", "type": "mcp",
        "base_url": "http://mcp.internal/rpc", "mcp_tools": tools})
    assert created.status_code == 200

    listing = client.get("/api/integrations").json()
    assert listing[0]["type"] == "mcp"
    assert listing[0]["tool_count"] == 1


def test_admin_token_enforced_on_api_not_page():
    reg = Registry([], None)
    app = FastAPI()
    app.include_router(build_router(reg, admin_token="sek"))
    client = TestClient(app)

    # the page shell stays reachable (it carries no data/secrets)
    assert client.get("/integrations").status_code != 401
    # the data/action API requires the token
    assert client.get("/api/integrations").status_code == 401
    assert client.get("/api/integrations",
                      headers={"X-Admin-Token": "sek"}).status_code == 200
    assert client.get("/api/integrations",
                      headers={"Authorization": "Bearer sek"}).status_code == 200
    assert client.get("/api/integrations",
                      headers={"Authorization": "Bearer wrong"}).status_code == 401
    # a register-a-tool POST is also gated
    assert client.post("/api/integrations", json={
        "name": "X", "base_url": "http://x",
        "operations": [{"operation_id": "o", "method": "get", "path": "/o"}]}
    ).status_code == 401
