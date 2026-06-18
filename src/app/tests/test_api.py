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
