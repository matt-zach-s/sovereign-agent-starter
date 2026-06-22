"""Tier 1: register in-VPC MCP servers as agent tools.

A small, dependency-free MCP client over the Streamable-HTTP transport — JSON-RPC
2.0 POSTed to the server URL. Like ``openapi_tools``/``dispatch`` it takes an
injectable httpx client, so discovery and tool calls are unit-testable offline.
It speaks the core of the protocol — ``initialize`` -> ``notifications/initialized``
-> ``tools/list`` -> ``tools/call`` — which is enough to discover and invoke tools
on a compliant in-boundary MCP server with no public-internet egress.

Documented simplifications (fork-it extensions): single JSON or single-event SSE
responses only (no long-lived server->client streaming); static auth headers only
(bearer / api-key, resolved from the in-boundary secret store — no OAuth handshake);
stdio transport unsupported (HTTP/in-VPC endpoints only).
"""
import json
import os
from typing import Optional

import httpx

from .models import Auth, McpTool, sanitize_tool_name

# Comma-separated list of MCP server URLs reachable inside the VPC. Used as an
# env-driven shortcut; the admin UI / ConfigMap is the richer path.
MCP_SERVER_URLS = [u.strip() for u in os.environ.get("MCP_SERVER_URLS", "").split(",") if u.strip()]

_PROTOCOL_VERSION = "2025-06-18"
_MAX = 4000


class McpError(Exception):
    pass


def _auth_headers(auth: Optional[Auth], secret: Optional[str]) -> dict:
    headers = {}
    if auth and secret:
        if auth.type == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        elif auth.type == "api_key_header" and auth.header:
            headers[auth.header] = secret
    return headers


class McpClient:
    """Minimal Streamable-HTTP MCP client. One instance == one server session."""

    def __init__(self, url: str, *, client: Optional[httpx.Client] = None,
                 headers: Optional[dict] = None):
        self.url = url
        self._headers = dict(headers or {})
        self._owns = client is None
        self._client = client or httpx.Client(timeout=30.0)
        self._session_id: Optional[str] = None
        self._id = 0

    def __enter__(self) -> "McpClient":
        self.initialize()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, payload: dict) -> Optional[dict]:
        headers = dict(self._headers)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json, text/event-stream"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        resp = self._client.post(self.url, headers=headers, json=payload)
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        if payload.get("id") is None:        # a notification expects no body
            return None
        if resp.status_code >= 400:
            raise McpError(f"HTTP {resp.status_code} from MCP server: {resp.text[:200]}")
        return _parse_rpc(resp)

    def initialize(self) -> dict:
        result = self._rpc("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "sovereign-agent-starter", "version": "0.1"},
        })
        self._notify("notifications/initialized", {})
        return result

    def _rpc(self, method: str, params: dict) -> dict:
        reply = self._post({"jsonrpc": "2.0", "id": self._next_id(),
                            "method": method, "params": params})
        if reply is None:
            raise McpError(f"empty response to {method}")
        if "error" in reply:
            err = reply["error"]
            raise McpError(f"{method} failed: {err.get('message', err)}")
        return reply.get("result", {})

    def _notify(self, method: str, params: dict) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params})

    def list_tools(self) -> list:
        result = self._rpc("tools/list", {})
        return [McpTool(
            name=t["name"],
            description=t.get("description", "") or "",
            input_schema=t.get("inputSchema") or {"type": "object", "properties": {}},
        ) for t in result.get("tools", [])]

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return _content_to_text(result)


def _parse_rpc(resp: httpx.Response) -> dict:
    """Parse a JSON-RPC reply from either a JSON body or a single-event SSE body."""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        data = None
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                data = line[len("data:"):].strip()
        if data is None:
            raise McpError("no data in SSE response")
        return json.loads(data)
    return resp.json()


def _content_to_text(result: dict) -> str:
    parts = []
    for block in result.get("content", []) or []:
        if isinstance(block, dict):
            parts.append(block.get("text", "") if block.get("type") == "text"
                         else json.dumps(block))
    text = "\n".join(p for p in parts if p) or json.dumps(result)
    if result.get("isError"):
        return f"tool error (MCP): {text[:_MAX]}"
    return text[:_MAX]


def discover_tools(url: str, auth: Optional[Auth] = None, secret: Optional[str] = None,
                   *, client: Optional[httpx.Client] = None) -> list:
    """Connect to an MCP server and return its tools as McpTool. Offline-testable
    by injecting ``client`` (e.g. an httpx.Client over a MockTransport)."""
    with McpClient(url, client=client, headers=_auth_headers(auth, secret)) as c:
        return c.list_tools()


def tools_for(integration) -> list:
    """MCP tools -> OpenAI tool defs (mirrors openapi_tools.tools_for)."""
    return [{"type": "function", "function": {
        "name": sanitize_tool_name(t.name),
        "description": t.description or t.name,
        "parameters": t.input_schema or {"type": "object", "properties": {}},
    }} for t in integration.mcp_tools]


def dispatch_mcp(integration, tool, args: dict, secret: Optional[str],
                 client: Optional[httpx.Client] = None) -> str:
    """Invoke one MCP tool on the integration's server (mirrors dispatch.dispatch).
    Errors are returned as text to feed back to the model, never raised."""
    try:
        with McpClient(integration.base_url, client=client,
                       headers=_auth_headers(integration.auth, secret)) as c:
            return c.call_tool(tool.name, dict(args or {}))
    except Exception as e:
        return f"tool error: {type(e).__name__}: {e}"


def load_mcp_tools():
    """Back-compat: env-driven discovery of MCP_SERVER_URLS. Returns tool defs.
    The richer path is a typed `mcp` integration (config or the admin UI)."""
    out = []
    for url in MCP_SERVER_URLS:
        try:
            for t in discover_tools(url):
                out.append({"type": "function", "function": {
                    "name": sanitize_tool_name(t.name),
                    "description": t.description or t.name,
                    "parameters": t.input_schema,
                }})
        except Exception:
            continue
    return out
