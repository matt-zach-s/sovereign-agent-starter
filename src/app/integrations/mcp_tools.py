"""Tier 1 extension point: register MCP servers as agent tools.

Stub by design. Fork and implement ``load_mcp_tools()`` to connect to one or more
Model Context Protocol (MCP) servers running inside the customer's environment
and expose their tools to the model. Set ``MCP_SERVER_URLS`` to a comma-separated
list of in-VPC MCP endpoints.

Return a list of OpenAI-compatible tool definitions (same shape as
``openapi_tools.load_openapi_tools``), and wire the dispatch side in main.py.
"""
import os

# Comma-separated list of MCP server URLs reachable inside the VPC.
MCP_SERVER_URLS = [u for u in os.environ.get("MCP_SERVER_URLS", "").split(",") if u]


def load_mcp_tools():
    # TODO (Tier 1): connect to each MCP server and return its tools as tool defs.
    return []
