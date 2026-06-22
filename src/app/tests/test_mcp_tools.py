import json
import httpx

from integrations.mcp_tools import discover_tools, dispatch_mcp, tools_for
from integrations.models import Auth, Integration, McpTool

TOOLS = [
    {"name": "list_tickets", "description": "List open tickets",
     "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}}}},
    {"name": "close_ticket", "description": "Close a ticket",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}}},
]


def make_server(*, sse=False, require_auth=None, record=None):
    """httpx MockTransport that speaks core MCP JSON-RPC over HTTP."""
    def handler(request):
        if require_auth is not None and request.headers.get("authorization") != require_auth:
            return httpx.Response(401, text="unauthorized")
        payload = json.loads(request.read())
        method = payload.get("method")
        if record is not None:
            record.append((method, payload.get("params")))
        if payload.get("id") is None:                       # notification
            return httpx.Response(202, text="")
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "fake"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = payload["params"]["name"]
            args = payload["params"].get("arguments", {})
            result = {"content": [{"type": "text",
                                   "text": f"{name}({json.dumps(args, sort_keys=True)}) ok"}]}
        else:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
                                             "error": {"code": -32601, "message": "no method"}})
        body = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        if sse:
            return httpx.Response(200, text=f"event: message\ndata: {json.dumps(body)}\n\n",
                                  headers={"content-type": "text/event-stream",
                                           "mcp-session-id": "sess-1"})
        return httpx.Response(200, json=body, headers={"mcp-session-id": "sess-1"})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_discover_tools_parses_tool_list():
    tools = discover_tools("http://mcp.internal/rpc", client=make_server())
    assert [t.name for t in tools] == ["list_tickets", "close_ticket"]
    assert tools[0].input_schema["properties"]["status"]["type"] == "string"


def test_discover_over_sse_transport():
    tools = discover_tools("http://mcp.internal/rpc", client=make_server(sse=True))
    assert [t.name for t in tools] == ["list_tickets", "close_ticket"]


def test_initialize_handshake_then_initialized_then_list():
    rec = []
    discover_tools("http://mcp.internal/rpc", client=make_server(record=rec))
    methods = [m for m, _ in rec]
    assert methods[0] == "initialize"
    assert "notifications/initialized" in methods
    assert "tools/list" in methods


def test_call_tool_returns_text_content():
    rec = []
    out = dispatch_mcp(
        Integration(name="Tickets", type="mcp", base_url="http://mcp.internal/rpc"),
        McpTool(name="close_ticket"), {"id": "7"}, None, client=make_server(record=rec))
    assert 'close_ticket({"id": "7"}) ok' in out
    assert ("tools/call", {"name": "close_ticket", "arguments": {"id": "7"}}) in rec


def test_bearer_auth_header_reaches_server():
    out = dispatch_mcp(
        Integration(name="T", type="mcp", base_url="http://mcp.internal/rpc",
                    auth=Auth(type="bearer", secret_ref="t")),
        McpTool(name="list_tickets"), {}, "tok-9",
        client=make_server(require_auth="Bearer tok-9"))
    assert "list_tickets" in out and "tool error" not in out


def test_dispatch_mcp_returns_error_text_not_raise():
    def handler(request):
        raise httpx.ConnectError("refused")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = dispatch_mcp(Integration(name="T", type="mcp", base_url="http://x"),
                       McpTool(name="t"), {}, None, client=client)
    assert out.startswith("tool error")


def test_tools_for_shapes_openai_defs():
    integ = Integration(name="T", type="mcp", base_url="http://x",
                        mcp_tools=[McpTool(name="list_tickets", description="List")])
    defs = tools_for(integ)
    assert defs[0]["type"] == "function"
    assert defs[0]["function"]["name"] == "list_tickets"
    assert defs[0]["function"]["description"] == "List"
