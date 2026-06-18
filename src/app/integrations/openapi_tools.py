"""Tier 1: turn an OpenAPI spec into agent tools.

Pure parsing — no network here (callers fetch spec text and pass it in), so this
is trivially testable. The selected operations are persisted in full (method,
path, params) so the running app never needs the spec endpoint at boot.
"""
import yaml

from .models import Operation, ParsedSpec, sanitize_tool_name

_METHODS = ("get", "post", "put", "patch", "delete")


def parse_spec(spec_text: str) -> ParsedSpec:
    try:
        doc = yaml.safe_load(spec_text)  # YAML is a superset of JSON
    except yaml.YAMLError as e:
        raise ValueError(f"could not parse spec: {e}")
    if not isinstance(doc, dict) or "paths" not in doc:
        raise ValueError("not an OpenAPI document (no 'paths')")

    title = (doc.get("info") or {}).get("title", "Untitled API")
    servers = doc.get("servers") or []
    server = servers[0]["url"] if servers and isinstance(servers[0], dict) else ""

    operations = []
    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in _METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId") or sanitize_tool_name(f"{method}_{path}")
            operations.append(Operation(
                operation_id=op_id, method=method, path=path,
                summary=op.get("summary", "") or op.get("description", ""),
                parameters=_params_schema(op),
            ))
    return ParsedSpec(title=title, server=server, operations=operations)


def _params_schema(op: dict) -> dict:
    """Flatten path/query params + a simple requestBody into one object schema."""
    props, required = {}, []
    for p in op.get("parameters", []) or []:
        if not isinstance(p, dict) or "name" not in p:
            continue
        props[p["name"]] = p.get("schema", {"type": "string"})
        if p.get("required"):
            required.append(p["name"])
    body = (((op.get("requestBody") or {}).get("content") or {})
            .get("application/json") or {}).get("schema")
    if isinstance(body, dict) and body.get("type") == "object":
        for name, schema in (body.get("properties") or {}).items():
            props[name] = schema
        required.extend(body.get("required", []))
    out = {"type": "object", "properties": props}
    if required:
        out["required"] = sorted(set(required))
    return out


def operation_to_tool(op: Operation) -> dict:
    return {"type": "function", "function": {
        "name": sanitize_tool_name(op.operation_id),
        "description": op.summary or f"{op.method.upper()} {op.path}",
        "parameters": op.parameters or {"type": "object", "properties": {}},
    }}


def tools_for(integration) -> list:
    return [operation_to_tool(o) for o in integration.operations]
