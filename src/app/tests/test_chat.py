import json
import types
import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_stub_model(monkeypatch, tmp_path):
    # config with one integration whose endpoint we mock via dispatch's client.
    import importlib, integrations.dispatch as dispatch_mod
    cfg = tmp_path / "integrations.yaml"
    cfg.write_text(
        "integrations:\n"
        "  - name: Inv\n"
        "    base_url: http://inv.internal/v1\n"
        "    auth: {type: none}\n"
        "    operations:\n"
        "      - {operation_id: getItems, method: get, path: /items}\n")
    monkeypatch.setenv("INTEGRATIONS_CONFIG", str(cfg))
    monkeypatch.setenv("INTEGRATIONS_SECRETS_DIR", "")

    import main
    importlib.reload(main)

    # Stub the model: first call asks for the tool, second call answers.
    calls = {"n": 0}

    def fake_create(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            tc = types.SimpleNamespace(
                id="call_1",
                function=types.SimpleNamespace(name="getItems", arguments="{}"))
            msg = types.SimpleNamespace(content=None, tool_calls=[tc])
        else:
            msg = types.SimpleNamespace(content="There are 2 items.", tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(main.client.chat.completions, "create", fake_create)

    # Make dispatch hit a mock endpoint instead of the network.
    def fake_dispatch(integration, op, args, secret, client=None):
        return 'HTTP 200\n[{"id":1},{"id":2}]'
    monkeypatch.setattr(main, "dispatch", fake_dispatch)

    return TestClient(main.app)


def test_chat_runs_tool_loop(app_with_stub_model):
    r = app_with_stub_model.post("/api/chat", json={
        "messages": [{"role": "user", "content": "how many items?"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "There are 2 items."
    assert body["trace"][0]["tool"] == "getItems"


def test_chat_without_tools_still_replies(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("INTEGRATIONS_CONFIG", str(tmp_path / "none.yaml"))
    import main
    importlib.reload(main)
    import types as t

    def fake_create(**kwargs):
        msg = t.SimpleNamespace(content="hello", tool_calls=None)
        return t.SimpleNamespace(choices=[t.SimpleNamespace(message=msg)])
    monkeypatch.setattr(main.client.chat.completions, "create", fake_create)
    r = TestClient(main.app).post("/api/chat",
                                  json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.json()["reply"] == "hello"
