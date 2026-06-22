"""FastAPI router for the integrations admin UI + JSON API."""
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .manifest import render_manifest
from .models import Auth, Integration, Operation
from .openapi_tools import parse_spec, tools_for


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


class CreateReq(BaseModel):
    name: str
    base_url: str
    auth: AuthReq = AuthReq()
    secret_value: Optional[str] = None
    operations: list[OpReq] = []
    spec_url: Optional[str] = None


def _summary(integ: Integration) -> dict:
    return {"id": integ.id, "name": integ.name, "type": integ.type,
            "base_url": integ.base_url, "enabled": integ.enabled,
            "tool_count": len(tools_for(integ)) if integ.enabled else 0,
            "source": integ.source, "auth_type": integ.auth.type}


def build_router(registry, *, http_client_factory=httpx.Client) -> APIRouter:
    r = APIRouter()

    @r.get("/integrations")
    def page():
        return FileResponse("static/integrations.html")

    @r.get("/api/integrations")
    def list_integrations():
        return [_summary(i) for i in registry.list()]

    @r.post("/api/integrations/parse")
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

    @r.post("/api/integrations/test")
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

    @r.post("/api/integrations")
    def create(req: CreateReq):
        integ = Integration(
            name=req.name, base_url=req.base_url,
            auth=Auth(type=req.auth.type, header=req.auth.header,
                      secret_ref=req.auth.secret_ref),
            operations=[Operation(o.operation_id, o.method, o.path, o.summary,
                                  o.parameters) for o in req.operations],
            spec_url=req.spec_url, source="session",
        )
        registry.add_session(integ, req.secret_value)
        return {"id": integ.id, "manifest": _manifest(registry)}

    @r.patch("/api/integrations/{id}")
    def patch(id: str, body: dict):
        if not registry.set_enabled(id, bool(body.get("enabled", True))):
            raise HTTPException(404, "not found")
        return {"ok": True}

    @r.delete("/api/integrations/{id}")
    def delete(id: str):
        if not registry.remove(id):
            raise HTTPException(400, "only session integrations can be removed")
        return {"ok": True}

    @r.get("/api/integrations/{id}/manifest")
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

    return r
