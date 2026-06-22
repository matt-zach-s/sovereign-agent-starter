"""Core data types for the integrations scaffold."""
import re
from dataclasses import dataclass, field
from typing import Optional


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return s.strip("-") or "integration"


def sanitize_tool_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
    return (s or "tool")[:64]


@dataclass
class Auth:
    type: str = "none"               # none | bearer | api_key_header
    header: Optional[str] = None     # for api_key_header
    secret_ref: Optional[str] = None # key into the mounted Secret

    @classmethod
    def from_dict(cls, d) -> "Auth":
        if not d:
            return cls()
        return cls(type=d.get("type", "none"),
                   header=d.get("header"), secret_ref=d.get("secret_ref"))

    def to_dict(self) -> dict:
        out = {"type": self.type}
        if self.header:
            out["header"] = self.header
        if self.secret_ref:
            out["secret_ref"] = self.secret_ref
        return out


@dataclass
class Operation:
    operation_id: str
    method: str
    path: str
    summary: str = ""
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})

    @classmethod
    def from_dict(cls, d) -> "Operation":
        return cls(operation_id=d["operation_id"], method=d["method"], path=d["path"],
                   summary=d.get("summary", ""),
                   parameters=d.get("parameters", {"type": "object", "properties": {}}))

    def to_dict(self) -> dict:
        return {"operation_id": self.operation_id, "method": self.method,
                "path": self.path, "summary": self.summary, "parameters": self.parameters}


@dataclass
class McpTool:
    """A tool discovered from an MCP server (type == "mcp" integrations)."""
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=lambda: {"type": "object", "properties": {}})

    @classmethod
    def from_dict(cls, d) -> "McpTool":
        return cls(name=d["name"], description=d.get("description", "") or "",
                   input_schema=d.get("input_schema")
                   or {"type": "object", "properties": {}})

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": self.input_schema}


@dataclass
class Integration:
    name: str
    type: str = "openapi"
    base_url: str = ""
    enabled: bool = True
    auth: Auth = field(default_factory=Auth)
    operations: list = field(default_factory=list)  # list[Operation] (type == "openapi")
    mcp_tools: list = field(default_factory=list)    # list[McpTool]   (type == "mcp")
    spec_url: Optional[str] = None
    source: str = "config"          # config | session
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = slugify(self.name)

    @classmethod
    def from_dict(cls, d) -> "Integration":
        return cls(
            name=d["name"], type=d.get("type", "openapi"),
            base_url=d.get("base_url", ""), enabled=d.get("enabled", True),
            auth=Auth.from_dict(d.get("auth")),
            operations=[Operation.from_dict(o) for o in d.get("operations", [])],
            mcp_tools=[McpTool.from_dict(t) for t in d.get("mcp_tools", [])],
            spec_url=d.get("spec_url"), source=d.get("source", "config"),
            id=d.get("id", ""),
        )

    def to_def_dict(self) -> dict:
        """Shape persisted into the ConfigMap's integrations.yaml."""
        out = {
            "name": self.name, "id": self.id, "type": self.type,
            "base_url": self.base_url, "enabled": self.enabled,
            "auth": self.auth.to_dict(),
        }
        if self.type == "mcp":
            out["mcp_tools"] = [t.to_dict() for t in self.mcp_tools]
        else:
            out["operations"] = [o.to_dict() for o in self.operations]
        if self.spec_url:
            out["spec_url"] = self.spec_url
        return out


@dataclass
class ParsedSpec:
    title: str
    server: str
    operations: list  # list[Operation]
