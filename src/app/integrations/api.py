"""FastAPI router for the integrations admin UI + JSON API.

App-level auth: when ``admin_token`` is set, every ``/api/integrations*`` route
requires it (``Authorization: Bearer <token>`` or ``X-Admin-Token: <token>``). The
page shell (``GET /integrations``) stays open so the browser can load the UI, which
then authenticates each call. With no token the API is open (local dev) and main.py
logs a loud warning — register-a-tool-that-holds-credentials is exactly the action
that must not be unauthenticated in a deployed, in-boundary posture.
"""
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .manifest import render_manifest
from .mcp_tools import discover_tools
from .models import Auth, Integration, McpTool, Operation
from .openapi_tools import parse_spec
from .providers import tools_for


class ParseReq(BaseModel):
    spec_url: Optional[str] = None
    spec_text: Optional[str] = None


class AuthReq(BaseModel):
    type: str = "none"
    header: Optional[str] = None
    secret_ref: Optional[str] = None


class TestReq(BaseModel):
    base_url: str
    auth: AuthReq = AuthReq()
    secret_value: Optional[str] = None


class OpReq(BaseModel):
    operation_id: str
    method: str
    path: str
    summary: str = ""
    parameters: dict = {"type": "object", "properties": {}}


class McpToolReq(BaseModel):
    name: str
    description: str = ""
    input_schema: dict = {"type": "object", "properties": {}}


class McpDiscoverReq(BaseModel):
    server_url: str
    auth: AuthReq = AuthReq()
    secret_value: Optional[str] = None


class CreateReq(BaseModel):
    name: str
    type: str = "openapi"               # openapi | mcp
    base_url: str = ""                  # for mcp: the in-VPC server URL
    auth: AuthReq = AuthReq()
    secret_value: Optional[str] = None
    operations: list[OpReq] = []        # openapi
    mcp_tools: list[McpToolReq] = []    # mcp
    spec_url: Optional[str] = None


def _summary(integ: Integration) -> dict:
    return {"id": integ.id, "name": integ.name, "type": integ.type,
            "base_url": integ.base_url, "enabled": integ.enabled,
            "tool_count": len(tools_for(integ)) if integ.enabled else 0,
            "source": integ.source, "auth_type": integ.auth.type}


def build_router(registry, *, admin_token: Optional[str] = None,
                 http_client_factory=httpx.Client, mcp_client_factory=None) -> APIRouter:
    r = APIRouter()

    @r.get("/integrations")
    def page():
        return FileResponse("static/integrations.html")

    # ---- app-level auth: gate the data/action API, not the page shell --------
    deps = []
    if admin_token:
        def require_admin(authorization: Optional[str] = Header(None),
                          x_admin_token: Optional[str] = Header(None)):
            token = x_admin_token
            if not token and authorization and authorization.lower().startswith("bearer "):
                token = authorization[7:]
            if token != admin_token:
                raise HTTPException(401, "admin authentication required")
        deps = [Depends(require_admin)]

    api = APIRouter(dependencies=deps)

    @api.get("/api/integrations")
    def list_integrations():
        return [_summary(i) for i in registry.list()]

    @api.post("/api/integrations/parse")
    def parse(req: ParseReq):
        text = req.spec_text
        if not text and req.spec_url:
            try:
                with http_client_factory(timeout=15.0) as c:
                    text = c.get(req.spec_url).text
            except Exception as e:
                raise HTTPException(400, f"could not fetch spec: {e}")
        if not text:
            raise HTTPException(400, "provide spec_url or spec_text")
        try:
            spec = parse_spec(text)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"title": spec.title, "server": spec.server,
                "operations": [o.to_dict() for o in spec.operations]}

    @api.post("/api/integrations/mcp/discover")
    def mcp_discover(req: McpDiscoverReq):
        auth = Auth(type=req.auth.type, header=req.auth.header, secret_ref=req.auth.secret_ref)
        try:
            client = mcp_client_factory() if mcp_client_factory else None
            tools = discover_tools(req.server_url, auth, req.secret_value, client=client)
        except Exception as e:
            raise HTTPException(400, f"could not reach MCP server: {e}")
        return {"server_url": req.server_url, "tools": [t.to_dict() for t in tools]}

    @api.post("/api/integrations/test")
    def test_conn(req: TestReq):
        headers = {}
        if req.auth.type == "bearer" and req.secret_value:
            headers["Authorization"] = f"Bearer {req.secret_value}"
        elif req.auth.type == "api_key_header" and req.auth.header and req.secret_value:
            headers[req.auth.header] = req.secret_value
        try:
            with http_client_factory(timeout=10.0) as c:
                resp = c.get(req.base_url, headers=headers)
            return {"ok": resp.status_code < 500, "status": resp.status_code,
                    "detail": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "status": 0, "detail": f"{type(e).__name__}: {e}"}

    @api.post("/api/integrations")
    def create(req: CreateReq):
        auth = Auth(type=req.auth.type, header=req.auth.header, secret_ref=req.auth.secret_ref)
        if req.type == "mcp":
            integ = Integration(
                name=req.name, type="mcp", base_url=req.base_url, auth=auth,
                mcp_tools=[McpTool(t.name, t.description, t.input_schema)
                           for t in req.mcp_tools],
                source="session",
            )
        else:
            integ = Integration(
                name=req.name, base_url=req.base_url, auth=auth,
                operations=[Operation(o.operation_id, o.method, o.path, o.summary,
                                      o.parameters) for o in req.operations],
                spec_url=req.spec_url, source="session",
            )
        registry.add_session(integ, req.secret_value)
        return {"id": integ.id, "manifest": _manifest(registry)}

    @api.patch("/api/integrations/{id}")
    def patch(id: str, body: dict):
        if not registry.set_enabled(id, bool(body.get("enabled", True))):
            raise HTTPException(404, "not found")
        return {"ok": True}

    @api.delete("/api/integrations/{id}")
    def delete(id: str):
        if not registry.remove(id):
            raise HTTPException(400, "only session integrations can be removed")
        return {"ok": True}

    @api.get("/api/integrations/{id}/manifest")
    def manifest(id: str):
        if not registry.get(id):
            raise HTTPException(404, "not found")
        return _manifest(registry)

    def _manifest(reg):
        integs = reg.list()
        secrets = {}
        for i in integs:
            ref = i.auth.secret_ref
            val = reg.secret_for(i)
            if ref and val is not None:
                secrets[ref] = val
        return render_manifest(integs, secrets)

    r.include_router(api)
    return r
