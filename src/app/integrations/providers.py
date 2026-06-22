"""Route an integration to its provider. Keeps the OpenAPI path unchanged while
adding MCP, so registry/main never branch on ``integration.type`` themselves.
"""
from . import mcp_tools, openapi_tools
from .models import sanitize_tool_name


def tools_for(integ) -> list:
    """OpenAI-compatible tool defs for one integration, by type."""
    if integ.type == "mcp":
        return mcp_tools.tools_for(integ)
    return openapi_tools.tools_for(integ)


def tool_refs(integ) -> list:
    """(sanitized_tool_name, ref) pairs; ref is an Operation or an McpTool."""
    if integ.type == "mcp":
        return [(sanitize_tool_name(t.name), t) for t in integ.mcp_tools]
    return [(sanitize_tool_name(o.operation_id), o) for o in integ.operations]
