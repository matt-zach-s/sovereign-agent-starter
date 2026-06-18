# Integrations UI Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal, teachable web UI that lets an operator wire an internal HTTP system into the self-hosted agent via its OpenAPI spec — no code edits, all in-VPC, secrets in-boundary.

**Architecture:** Flesh out `src/app/integrations/` into small single-purpose modules (models, openapi parsing, config loading, an in-memory registry, dispatch, manifest rendering, and an admin API router). `main.py` mounts the router and runs a tool-call loop. A new `/integrations` static page registers integrations from an OpenAPI spec; the app never writes to the cluster — it emits ConfigMap+Secret YAML to persist. The chat backend becomes stateless+conversation-aware; the chat page persists history to localStorage.

**Tech Stack:** Python 3.12, FastAPI, the OpenAI client (pointed at self-hosted Ollama), httpx (sync), PyYAML, pytest. Vanilla HTML/CSS/JS frontend (no framework).

## Global Constraints

- Python base image: `python:3.12-slim` (per `src/app/Dockerfile`).
- Pinned deps (do not bump): `fastapi==0.115.0`, `uvicorn==0.30.6`, `openai==1.51.0`, `httpx==0.27.2`, `pydantic==2.9.2`, `typing_extensions>=4.13.0`. **Add `pyyaml==6.0.2`.** Dev-only: `pytest==8.3.3`.
- All code is **synchronous** (existing `main.py` uses sync `def` handlers and the sync OpenAI client). Use `httpx.Client`, not `AsyncClient`.
- Auth types supported: **`none` | `bearer` | `api_key_header`** only. No OAuth/Basic/mTLS.
- Type is **`openapi`** only; `mcp` stays a stub ("coming next").
- **Secrets never reach the browser on read.** Plaintext secret values appear only: (a) in the operator's typed input, (b) once in the emitted Secret YAML. No GET endpoint returns a secret value.
- Tool names sent to the model must match `^[a-zA-Z0-9_-]{1,64}$` — sanitize operationIds.
- Tool-call loop is **capped at 5 iterations**.
- Admin API + page are gated behind env `ENABLE_INTEGRATIONS_ADMIN` (default `"true"`).
- Kubernetes namespace is `agent`; chatbot Deployment is named `chatbot` (per `src/charts/chatbot/`).
- Config paths (env, with defaults): `INTEGRATIONS_CONFIG=/etc/chatbot/integrations.yaml`, `INTEGRATIONS_SECRETS_DIR=/etc/chatbot/secrets`.
- Work on branch `integrations-ui-scaffold` (already created). Commit after every task.

**Planning refinement over the spec (intentional):** the persisted integration def stores the **full selected operation objects** (operationId, method, path, summary, parameters schema), not just operationIds. This keeps the running app **self-contained at boot** (no dependency on the spec endpoint being reachable at startup — better for air-gap); the API endpoint is only hit at actual tool-call time. The mockup's `operations: [id, id]` was illustrative.

**Dispatch heuristic (intentional simplification, documented in code):** to avoid modeling every OpenAPI parameter location, dispatch substitutes any argument matching a `{name}` placeholder in the path, then for `GET`/`DELETE` sends remaining args as query params and for `POST`/`PUT`/`PATCH` sends them as a JSON body. Good enough for a teachable starter; noted as a limitation in `dispatch.py`.

---

## File Structure

**Create:**
- `src/app/integrations/models.py` — dataclasses: `Auth`, `Operation`, `Integration`, `ParsedSpec`; `slugify`, `sanitize_tool_name`.
- `src/app/integrations/openapi_tools.py` — replace stub: `parse_spec`, `operation_to_tool`, `tools_for`.
- `src/app/integrations/config.py` — `load_integrations`, `read_secret`.
- `src/app/integrations/registry.py` — `Registry` class.
- `src/app/integrations/dispatch.py` — `dispatch`.
- `src/app/integrations/manifest.py` — `render_manifest`.
- `src/app/integrations/api.py` — `build_router(registry)`.
- `src/app/static/integrations.html` — the admin page.
- `src/app/tests/__init__.py`, `src/app/tests/conftest.py`, plus one test file per module.
- `src/app/requirements-dev.txt` — `pytest==8.3.3`.
- `src/charts/chatbot/templates/configmap-integrations.yaml`, `src/charts/chatbot/templates/secret-integrations.yaml`.

**Modify:**
- `src/app/requirements.txt` — add `pyyaml==6.0.2`.
- `src/app/main.py` — mount router; conversation-aware `/api/chat` + tool-call loop.
- `src/app/static/index.html` — localStorage history, Clear chat, nav link.
- `src/app/integrations/mcp_tools.py` — keep stub; tiny docstring touch only if needed (no behavior change).
- `src/charts/chatbot/templates/deployment.yaml` — env + volume mounts.
- `src/charts/chatbot/values.yaml`, `components/values/chatbot.yaml` — integrations blocks.
- `src/app/integrations/README.md`, top-level `README.md` — reflect that the UI exists.

Test command baseline (run from `src/app/`): `python -m pytest -q`.

---

## Task 1: Test harness + core models

**Files:**
- Create: `src/app/integrations/models.py`
- Create: `src/app/requirements-dev.txt`
- Create: `src/app/tests/__init__.py` (empty), `src/app/tests/conftest.py`
- Test: `src/app/tests/test_models.py`

**Interfaces:**
- Produces:
  - `slugify(name: str) -> str`
  - `sanitize_tool_name(name: str) -> str`
  - `@dataclass Auth(type="none", header=None, secret_ref=None)` + `Auth.from_dict(d)->Auth`, `Auth.to_dict()->dict`
  - `@dataclass Operation(operation_id, method, path, summary="", parameters=dict)` + `from_dict`/`to_dict`
  - `@dataclass Integration(name, type="openapi", base_url="", enabled=True, auth=Auth, operations=list[Operation], spec_url=None, source="config", id="")` + `from_dict(d)->Integration`, `to_def_dict()->dict` (the ConfigMap shape)
  - `@dataclass ParsedSpec(title, server, operations: list[Operation])`

- [ ] **Step 1: Create dev requirements and test package**

Create `src/app/requirements-dev.txt`:
```
pytest==8.3.3
```
Create empty `src/app/tests/__init__.py`. Create `src/app/tests/conftest.py`:
```python
import os
import sys

# Make `import integrations...` and `import main` work when running pytest
# from src/app/ (mirrors PYTHONPATH=/opt/deps + app root at runtime).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

- [ ] **Step 2: Write the failing test**

Create `src/app/tests/test_models.py`:
```python
from integrations.models import (
    Auth, Operation, Integration, ParsedSpec, slugify, sanitize_tool_name,
)


def test_slugify_and_tool_name():
    assert slugify("Inventory API") == "inventory-api"
    assert sanitize_tool_name("get/items {weird}") == "get_items_weird"


def test_auth_roundtrip_drops_empty():
    a = Auth.from_dict({"type": "api_key_header", "header": "X-API-Key",
                        "secret_ref": "inventory-api-key"})
    assert a.to_dict() == {"type": "api_key_header", "header": "X-API-Key",
                           "secret_ref": "inventory-api-key"}
    assert Auth.from_dict(None).to_dict() == {"type": "none"}


def test_integration_def_dict_uses_full_operations():
    op = Operation(operation_id="getItem", method="get", path="/items/{id}",
                   summary="Get one", parameters={"type": "object", "properties": {}})
    integ = Integration(name="Inventory API", base_url="http://inv.internal/v1",
                        operations=[op], auth=Auth(type="bearer", secret_ref="inv-token"))
    d = integ.to_def_dict()
    assert d["name"] == "Inventory API"
    assert d["id"] == "inventory-api"
    assert d["operations"][0]["operation_id"] == "getItem"
    assert d["auth"] == {"type": "bearer", "secret_ref": "inv-token"}
    # round-trips back
    assert Integration.from_dict(d).operations[0].path == "/items/{id}"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'integrations.models'`.

- [ ] **Step 4: Write minimal implementation**

Create `src/app/integrations/models.py`:
```python
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
class Integration:
    name: str
    type: str = "openapi"
    base_url: str = ""
    enabled: bool = True
    auth: Auth = field(default_factory=Auth)
    operations: list = field(default_factory=list)  # list[Operation]
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
            spec_url=d.get("spec_url"), source=d.get("source", "config"),
            id=d.get("id", ""),
        )

    def to_def_dict(self) -> dict:
        """Shape persisted into the ConfigMap's integrations.yaml."""
        out = {
            "name": self.name, "id": self.id, "type": self.type,
            "base_url": self.base_url, "enabled": self.enabled,
            "auth": self.auth.to_dict(),
            "operations": [o.to_dict() for o in self.operations],
        }
        if self.spec_url:
            out["spec_url"] = self.spec_url
        return out


@dataclass
class ParsedSpec:
    title: str
    server: str
    operations: list  # list[Operation]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_models.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/app/integrations/models.py src/app/requirements-dev.txt src/app/tests/
git commit -m "feat(integrations): core models + test harness"
```

---

## Task 2: OpenAPI spec parsing → operations + tool defs

**Files:**
- Modify (replace stub): `src/app/integrations/openapi_tools.py`
- Modify: `src/app/requirements.txt` (add `pyyaml==6.0.2`)
- Test: `src/app/tests/test_openapi_tools.py`

**Interfaces:**
- Consumes: `Operation`, `ParsedSpec`, `sanitize_tool_name` (Task 1).
- Produces:
  - `parse_spec(spec_text: str) -> ParsedSpec` — accepts JSON or YAML OpenAPI text.
  - `operation_to_tool(op: Operation) -> dict` — OpenAI tool def.
  - `tools_for(integration: Integration) -> list[dict]` — tool defs for the integration's operations.

- [ ] **Step 1: Add the YAML dependency**

Edit `src/app/requirements.txt`, add a line:
```
pyyaml==6.0.2
```

- [ ] **Step 2: Write the failing test**

Create `src/app/tests/test_openapi_tools.py`:
```python
import json
from integrations.models import Integration, Operation, Auth
from integrations.openapi_tools import parse_spec, operation_to_tool, tools_for

SPEC = json.dumps({
    "openapi": "3.0.0",
    "info": {"title": "Inventory API", "version": "1"},
    "servers": [{"url": "http://inv.internal/v1"}],
    "paths": {
        "/items": {"get": {"operationId": "getItems", "summary": "List items"}},
        "/items/{id}": {
            "get": {
                "operationId": "getItem", "summary": "Get one",
                "parameters": [{"name": "id", "in": "path", "required": True,
                                "schema": {"type": "string"}}],
            },
            "delete": {"summary": "Delete"},  # no operationId -> derived name
        },
    },
})


def test_parse_spec_lists_operations_and_title():
    spec = parse_spec(SPEC)
    assert spec.title == "Inventory API"
    assert spec.server == "http://inv.internal/v1"
    ids = {o.operation_id for o in spec.operations}
    assert "getItems" in ids and "getItem" in ids
    # operationId-less op gets a derived, stable name
    assert any(o.method == "delete" and o.path == "/items/{id}" for o in spec.operations)


def test_get_item_tool_has_path_param():
    spec = parse_spec(SPEC)
    op = next(o for o in spec.operations if o.operation_id == "getItem")
    tool = operation_to_tool(op)
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "getItem"
    assert "id" in tool["function"]["parameters"]["properties"]
    assert tool["function"]["parameters"]["required"] == ["id"]


def test_tools_for_only_includes_integration_operations():
    op = Operation(operation_id="getItems", method="get", path="/items")
    integ = Integration(name="Inv", base_url="http://x", operations=[op])
    tools = tools_for(integ)
    assert len(tools) == 1 and tools[0]["function"]["name"] == "getItems"


def test_parse_spec_rejects_garbage():
    try:
        parse_spec("not a spec at all: [")
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_openapi_tools.py -q`
Expected: FAIL — `load_openapi_tools` exists but `parse_spec` does not (ImportError).

- [ ] **Step 4: Write minimal implementation**

Replace `src/app/integrations/openapi_tools.py` entirely:
```python
"""Tier 1: turn an OpenAPI spec into agent tools.

Pure parsing — no network here (callers fetch spec text and pass it in), so this
is trivially testable. The selected operations are persisted in full (method,
path, params) so the running app never needs the spec endpoint at boot.
"""
import json

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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd src/app && pip install pyyaml==6.0.2 && python -m pytest tests/test_openapi_tools.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/app/integrations/openapi_tools.py src/app/requirements.txt src/app/tests/test_openapi_tools.py
git commit -m "feat(integrations): parse OpenAPI specs into tool defs"
```

---

## Task 3: Config loading (ConfigMap + Secret dir)

**Files:**
- Create: `src/app/integrations/config.py`
- Test: `src/app/tests/test_config.py`

**Interfaces:**
- Consumes: `Integration` (Task 1).
- Produces:
  - `load_integrations(config_path: Optional[str], secrets_dir: Optional[str]) -> list[Integration]` — reads the YAML file's top-level `integrations:` list; returns `[]` if path is unset/missing.
  - `read_secret(secrets_dir: Optional[str], ref: Optional[str]) -> Optional[str]` — reads `<secrets_dir>/<ref>` (file), stripping a trailing newline; `None` if unset/missing.

- [ ] **Step 1: Write the failing test**

Create `src/app/tests/test_config.py`:
```python
import textwrap
from integrations.config import load_integrations, read_secret


def test_load_integrations_from_yaml(tmp_path):
    cfg = tmp_path / "integrations.yaml"
    cfg.write_text(textwrap.dedent("""
        integrations:
          - name: Inventory API
            base_url: http://inv.internal/v1
            auth: {type: bearer, secret_ref: inv-token}
            operations:
              - {operation_id: getItems, method: get, path: /items}
    """))
    integs = load_integrations(str(cfg), None)
    assert len(integs) == 1
    assert integs[0].id == "inventory-api"
    assert integs[0].source == "config"
    assert integs[0].operations[0].operation_id == "getItems"


def test_load_integrations_missing_path_returns_empty():
    assert load_integrations(None, None) == []
    assert load_integrations("/nonexistent/x.yaml", None) == []


def test_read_secret(tmp_path):
    (tmp_path / "inv-token").write_text("s3cr3t\n")
    assert read_secret(str(tmp_path), "inv-token") == "s3cr3t"
    assert read_secret(str(tmp_path), "missing") is None
    assert read_secret(None, "inv-token") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_config.py -q`
Expected: FAIL — `No module named 'integrations.config'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/app/integrations/config.py`:
```python
"""Load integration defs from the mounted ConfigMap and secrets from the Secret."""
import os
from typing import Optional

import yaml

from .models import Integration


def load_integrations(config_path: Optional[str], secrets_dir: Optional[str]) -> list:
    if not config_path or not os.path.isfile(config_path):
        return []
    with open(config_path) as f:
        doc = yaml.safe_load(f) or {}
    out = []
    for d in (doc.get("integrations") or []):
        d.setdefault("source", "config")
        out.append(Integration.from_dict(d))
    return out


def read_secret(secrets_dir: Optional[str], ref: Optional[str]) -> Optional[str]:
    if not secrets_dir or not ref:
        return None
    path = os.path.join(secrets_dir, ref)
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return f.read().rstrip("\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_config.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/app/integrations/config.py src/app/tests/test_config.py
git commit -m "feat(integrations): load defs from ConfigMap + secrets from Secret dir"
```

---

## Task 4: In-memory registry

**Files:**
- Create: `src/app/integrations/registry.py`
- Test: `src/app/tests/test_registry.py`

**Interfaces:**
- Consumes: `Integration`, `Operation` (Task 1); `tools_for` (Task 2); `read_secret` (Task 3).
- Produces: class `Registry`:
  - `Registry(integrations: list[Integration], secrets_dir: Optional[str])`
  - `list() -> list[Integration]`
  - `get(id: str) -> Optional[Integration]`
  - `add_session(integ: Integration, secret_value: Optional[str]) -> Integration` — sets `source="session"`, stores secret in memory keyed by `auth.secret_ref`.
  - `set_enabled(id: str, enabled: bool) -> bool`
  - `remove(id: str) -> bool` — session integrations only; returns False for config ones.
  - `secret_for(integ: Integration) -> Optional[str]` — in-memory first, else `read_secret`.
  - `tools() -> list[dict]` — tool defs across enabled integrations.
  - `tool_index() -> dict[str, tuple[Integration, Operation]]` — sanitized tool name → (integration, op).

- [ ] **Step 1: Write the failing test**

Create `src/app/tests/test_registry.py`:
```python
from integrations.models import Integration, Operation, Auth
from integrations.registry import Registry


def _integ(name="Inv", enabled=True, source="config"):
    op = Operation(operation_id="getItems", method="get", path="/items")
    return Integration(name=name, base_url="http://x", enabled=enabled,
                       operations=[op], source=source)


def test_tools_only_for_enabled():
    reg = Registry([_integ(enabled=True), _integ(name="Off", enabled=False)], None)
    names = [t["function"]["name"] for t in reg.tools()]
    assert names == ["getItems"]  # only the enabled one


def test_set_enabled_toggles_tools():
    reg = Registry([_integ()], None)
    assert reg.set_enabled("inv", False) is True
    assert reg.tools() == []
    assert reg.set_enabled("nope", True) is False


def test_add_session_stores_secret_in_memory():
    reg = Registry([], None)
    integ = Integration(name="Tickets", base_url="http://t",
                        auth=Auth(type="bearer", secret_ref="tickets-token"),
                        operations=[Operation("list", "get", "/t")])
    reg.add_session(integ, "tok-123")
    assert reg.get("tickets").source == "session"
    assert reg.secret_for(reg.get("tickets")) == "tok-123"


def test_remove_session_only():
    reg = Registry([_integ(source="config")], None)
    assert reg.remove("inv") is False          # config-sourced: protected
    s = Integration(name="S", base_url="http://x",
                    operations=[Operation("o", "get", "/")], source="session")
    reg.add_session(s, None)
    assert reg.remove("s") is True


def test_tool_index_maps_name_to_op():
    reg = Registry([_integ()], None)
    idx = reg.tool_index()
    integ, op = idx["getItems"]
    assert op.path == "/items" and integ.id == "inv"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_registry.py -q`
Expected: FAIL — `No module named 'integrations.registry'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/app/integrations/registry.py`:
```python
"""In-memory registry of integrations (config-loaded + session-added)."""
from typing import Optional

from .config import read_secret
from .models import sanitize_tool_name
from .openapi_tools import tools_for


class Registry:
    def __init__(self, integrations: list, secrets_dir: Optional[str]):
        self._integrations = list(integrations)
        self._secrets_dir = secrets_dir
        self._session_secrets: dict = {}  # secret_ref -> value (process memory only)

    def list(self) -> list:
        return list(self._integrations)

    def get(self, id: str):
        return next((i for i in self._integrations if i.id == id), None)

    def add_session(self, integ, secret_value: Optional[str]):
        integ.source = "session"
        # replace any existing with the same id
        self._integrations = [i for i in self._integrations if i.id != integ.id]
        self._integrations.append(integ)
        if integ.auth.secret_ref and secret_value is not None:
            self._session_secrets[integ.auth.secret_ref] = secret_value
        return integ

    def set_enabled(self, id: str, enabled: bool) -> bool:
        integ = self.get(id)
        if not integ:
            return False
        integ.enabled = enabled
        return True

    def remove(self, id: str) -> bool:
        integ = self.get(id)
        if not integ or integ.source != "session":
            return False
        self._integrations = [i for i in self._integrations if i.id != id]
        self._session_secrets.pop(integ.auth.secret_ref, None)
        return True

    def secret_for(self, integ) -> Optional[str]:
        ref = integ.auth.secret_ref
        if not ref:
            return None
        if ref in self._session_secrets:
            return self._session_secrets[ref]
        return read_secret(self._secrets_dir, ref)

    def tools(self) -> list:
        out = []
        for integ in self._integrations:
            if integ.enabled:
                out.extend(tools_for(integ))
        return out

    def tool_index(self) -> dict:
        idx = {}
        for integ in self._integrations:
            if not integ.enabled:
                continue
            for op in integ.operations:
                idx[sanitize_tool_name(op.operation_id)] = (integ, op)
        return idx
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_registry.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/app/integrations/registry.py src/app/tests/test_registry.py
git commit -m "feat(integrations): in-memory registry with session secrets"
```

---

## Task 5: Tool-call dispatch to the in-VPC endpoint

**Files:**
- Create: `src/app/integrations/dispatch.py`
- Test: `src/app/tests/test_dispatch.py`

**Interfaces:**
- Consumes: `Integration`, `Operation`, `Auth` (Task 1).
- Produces:
  - `dispatch(integration: Integration, op: Operation, args: dict, secret: Optional[str], client: Optional[httpx.Client] = None) -> str` — performs the HTTP call, returns a string suitable as a `tool` message (response body, truncated to 4000 chars), or a `"tool error: ..."` string on failure. Never raises.

- [ ] **Step 1: Write the failing test**

Create `src/app/tests/test_dispatch.py`:
```python
import httpx
from integrations.models import Integration, Operation, Auth
from integrations.dispatch import dispatch


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")


def test_path_substitution_and_auth_header():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"id": "42", "name": "Widget"})

    integ = Integration(name="Inv", base_url="http://inv.internal/v1",
                        auth=Auth(type="bearer", secret_ref="t"))
    op = Operation(operation_id="getItem", method="get", path="/items/{id}")
    out = dispatch(integ, op, {"id": "42"}, "tok-9", client=_client(handler))
    assert "Widget" in out
    assert seen["url"] == "http://inv.internal/v1/items/42"
    assert seen["auth"] == "Bearer tok-9"


def test_api_key_header_and_query_params():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, text="ok")

    integ = Integration(name="Inv", base_url="http://inv/v1",
                        auth=Auth(type="api_key_header", header="X-API-Key", secret_ref="k"))
    op = Operation(operation_id="getItems", method="get", path="/items")
    dispatch(integ, op, {"limit": 5}, "abc", client=_client(handler))
    assert seen["key"] == "abc"
    assert "limit=5" in seen["url"]


def test_post_sends_json_body():
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(201, text="created")

    integ = Integration(name="Inv", base_url="http://inv/v1", auth=Auth())
    op = Operation(operation_id="reserve", method="post", path="/items/{id}/reserve")
    out = dispatch(integ, op, {"id": "7", "qty": 3}, None, client=_client(handler))
    assert "created" in out
    assert '"qty": 3' in seen["body"] and "id" not in seen["body"]  # id went to path


def test_errors_are_returned_not_raised():
    def handler(request):
        raise httpx.ConnectError("refused")

    integ = Integration(name="Inv", base_url="http://inv/v1", auth=Auth())
    op = Operation(operation_id="x", method="get", path="/x")
    out = dispatch(integ, op, {}, None, client=_client(handler))
    assert out.startswith("tool error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_dispatch.py -q`
Expected: FAIL — `No module named 'integrations.dispatch'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/app/integrations/dispatch.py`:
```python
"""Execute a model tool call against the real in-VPC endpoint.

Simplification (documented): args matching a {placeholder} in the path are
substituted there; for GET/DELETE the rest become query params, for
POST/PUT/PATCH a JSON body. Good enough for the starter; richer OpenAPI
parameter handling is a fork-it extension.
"""
import re
from typing import Optional

import httpx

_MAX = 4000


def dispatch(integration, op, args: dict, secret: Optional[str],
             client: Optional[httpx.Client] = None) -> str:
    args = dict(args or {})
    path = op.path
    for name in re.findall(r"{([^}]+)}", op.path):
        if name in args:
            path = path.replace("{" + name + "}", str(args.pop(name)))

    url = integration.base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {}
    a = integration.auth
    if a.type == "bearer" and secret:
        headers["Authorization"] = f"Bearer {secret}"
    elif a.type == "api_key_header" and a.header and secret:
        headers[a.header] = secret

    method = op.method.lower()
    kwargs = {"headers": headers, "timeout": 30.0}
    if method in ("get", "delete"):
        kwargs["params"] = args
    else:
        kwargs["json"] = args

    owns_client = client is None
    client = client or httpx.Client()
    try:
        resp = client.request(method, url, **kwargs)
        body = resp.text[:_MAX]
        return f"HTTP {resp.status_code}\n{body}"
    except Exception as e:  # network/timeout/etc — feed back to the model
        return f"tool error: {type(e).__name__}: {e}"
    finally:
        if owns_client:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_dispatch.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/app/integrations/dispatch.py src/app/tests/test_dispatch.py
git commit -m "feat(integrations): dispatch tool calls to in-VPC endpoints"
```

---

## Task 6: Manifest (ConfigMap + Secret YAML) generation

**Files:**
- Create: `src/app/integrations/manifest.py`
- Test: `src/app/tests/test_manifest.py`

**Interfaces:**
- Consumes: `Integration` (Task 1).
- Produces:
  - `render_manifest(integrations: list[Integration], secrets: dict[str, str], configmap_name="chatbot-integrations", secret_name="chatbot-integration-secrets") -> dict` → `{"configmap_yaml": str, "secret_yaml": str}`. The ConfigMap embeds `integrations.yaml` (the full current def set). The Secret embeds `stringData` for every `secret_ref` present in `secrets`. If no secrets, `secret_yaml` is `""`.

- [ ] **Step 1: Write the failing test**

Create `src/app/tests/test_manifest.py`:
```python
import yaml
from integrations.models import Integration, Operation, Auth
from integrations.manifest import render_manifest


def test_configmap_contains_defs_and_secret_has_values():
    integ = Integration(name="Inventory API", base_url="http://inv/v1",
                        auth=Auth(type="api_key_header", header="X-API-Key",
                                  secret_ref="inventory-api-key"),
                        operations=[Operation("getItems", "get", "/items")])
    out = render_manifest([integ], {"inventory-api-key": "s3cr3t"})

    cm = yaml.safe_load(out["configmap_yaml"])
    assert cm["kind"] == "ConfigMap"
    assert cm["metadata"]["name"] == "chatbot-integrations"
    embedded = yaml.safe_load(cm["data"]["integrations.yaml"])
    assert embedded["integrations"][0]["name"] == "Inventory API"
    # secret value must NOT leak into the ConfigMap
    assert "s3cr3t" not in out["configmap_yaml"]

    sec = yaml.safe_load(out["secret_yaml"])
    assert sec["kind"] == "Secret"
    assert sec["stringData"]["inventory-api-key"] == "s3cr3t"


def test_no_secrets_yields_empty_secret_yaml():
    integ = Integration(name="Open", base_url="http://x", auth=Auth(),
                        operations=[Operation("o", "get", "/")])
    out = render_manifest([integ], {})
    assert out["secret_yaml"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_manifest.py -q`
Expected: FAIL — `No module named 'integrations.manifest'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/app/integrations/manifest.py`:
```python
"""Render the ConfigMap + Secret YAML an operator applies to persist integrations.

The app never writes to the cluster; it hands the operator this config to apply
(kubectl) or commit to their Nuon app. Secret values appear ONLY here, never in
the ConfigMap and never in any GET response.
"""
import yaml


def render_manifest(integrations: list, secrets: dict,
                    configmap_name: str = "chatbot-integrations",
                    secret_name: str = "chatbot-integration-secrets") -> dict:
    defs = {"integrations": [i.to_def_dict() for i in integrations]}
    embedded = yaml.safe_dump(defs, sort_keys=False, default_flow_style=False)
    configmap = {
        "apiVersion": "v1", "kind": "ConfigMap",
        "metadata": {"name": configmap_name},
        "data": {"integrations.yaml": embedded},
    }
    configmap_yaml = yaml.safe_dump(configmap, sort_keys=False)

    secret_yaml = ""
    if secrets:
        secret = {
            "apiVersion": "v1", "kind": "Secret",
            "metadata": {"name": secret_name}, "type": "Opaque",
            "stringData": dict(secrets),
        }
        secret_yaml = yaml.safe_dump(secret, sort_keys=False)
    return {"configmap_yaml": configmap_yaml, "secret_yaml": secret_yaml}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_manifest.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/app/integrations/manifest.py src/app/tests/test_manifest.py
git commit -m "feat(integrations): render ConfigMap+Secret YAML to persist"
```

---

## Task 7: Admin API router

**Files:**
- Create: `src/app/integrations/api.py`
- Test: `src/app/tests/test_api.py`

**Interfaces:**
- Consumes: `Registry` (Task 4); `parse_spec` (Task 2); `Integration`, `Operation`, `Auth` (Task 1); `render_manifest` (Task 6); `dispatch` not needed here.
- Produces:
  - `build_router(registry: Registry, *, http_client_factory=httpx.Client) -> fastapi.APIRouter` mounting:
    - `GET /api/integrations`, `POST /api/integrations/parse`, `POST /api/integrations/test`, `POST /api/integrations`, `PATCH /api/integrations/{id}`, `DELETE /api/integrations/{id}`, `GET /api/integrations/{id}/manifest`, `GET /integrations` (serves `static/integrations.html`).
  - Pydantic models `ParseReq`, `TestReq`, `CreateReq` (used by Task 8 too).

- [ ] **Step 1: Write the failing test**

Create `src/app/tests/test_api.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_api.py -q`
Expected: FAIL — `No module named 'integrations.api'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/app/integrations/api.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_api.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/app/integrations/api.py src/app/tests/test_api.py
git commit -m "feat(integrations): admin API router (parse/test/create/toggle/delete)"
```

---

## Task 8: Wire the router + conversation-aware chat with tool-call loop

**Files:**
- Modify: `src/app/main.py`
- Test: `src/app/tests/test_chat.py`

**Interfaces:**
- Consumes: `Registry` (Task 4); `build_router` (Task 7); `dispatch` (Task 5).
- Produces:
  - `build_registry() -> Registry` (reads env `INTEGRATIONS_CONFIG`, `INTEGRATIONS_SECRETS_DIR`).
  - `/api/chat` accepts `{"messages": [{"role","content"}, ...]}`; runs the tool-call loop; returns `{"reply": str, "trace": [ {tool, args, result_preview}... ]}`.
  - Module globals `app`, `registry`, `client`, `MODEL` (so tests can monkeypatch `main.client`).

- [ ] **Step 1: Write the failing test**

Create `src/app/tests/test_chat.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_chat.py -q`
Expected: FAIL — `/api/chat` still expects `{message}` / returns no `trace`; `main.dispatch` undefined.

- [ ] **Step 3: Write the implementation**

Replace `src/app/main.py` with:
```python
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI

from integrations.config import load_integrations
from integrations.registry import Registry
from integrations.api import build_router
from integrations.dispatch import dispatch

# --- The swap layer ---------------------------------------------------------
BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.environ.get("OPENAI_API_KEY", "ollama")
MODEL = os.environ.get("MODEL", "llama3.2:3b")
ENABLE_ADMIN = os.environ.get("ENABLE_INTEGRATIONS_ADMIN", "true").lower() == "true"
MAX_TOOL_ITERS = 5

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


def build_registry() -> Registry:
    integs = load_integrations(os.environ.get("INTEGRATIONS_CONFIG"),
                               os.environ.get("INTEGRATIONS_SECRETS_DIR"))
    return Registry(integs, os.environ.get("INTEGRATIONS_SECRETS_DIR"))


registry = build_registry()

app = FastAPI(title="BYOC Agent Starter — chatbot")
if ENABLE_ADMIN:
    app.include_router(build_router(registry))

SYSTEM = ("You are a helpful assistant running fully self-hosted, inside the "
          "customer's own cloud. When tools are available, use them to answer "
          "questions about the customer's internal systems.")


class ChatRequest(BaseModel):
    messages: list[dict] = []


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "base_url": BASE_URL,
            "tools": len(registry.tools())}


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/api/chat")
def chat(req: ChatRequest):
    tools = registry.tools()
    idx = registry.tool_index()
    messages = [{"role": "system", "content": SYSTEM}] + req.messages
    trace = []
    try:
        for _ in range(MAX_TOOL_ITERS):
            kwargs = {"model": MODEL, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            resp = client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                return {"reply": msg.content or "", "trace": trace}
            # record the assistant tool-call turn, then answer each call
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [
                                 {"id": tc.id, "type": "function",
                                  "function": {"name": tc.function.name,
                                               "arguments": tc.function.arguments}}
                                 for tc in tool_calls]})
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = _json_args(tc.function.arguments)
                except ValueError:
                    args = {}
                pair = idx.get(name)
                if pair is None:
                    result = f"tool error: unknown tool {name}"
                else:
                    integ, op = pair
                    result = dispatch(integ, op, args, registry.secret_for(integ))
                trace.append({"tool": name, "args": args, "result_preview": result[:200]})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "name": name, "content": result})
        return {"reply": "(stopped: tool-call limit reached)", "trace": trace}
    except Exception as e:
        return JSONResponse(status_code=503,
                            content={"error": f"model not ready or unreachable: {e}"})


def _json_args(raw):
    import json
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("bad tool arguments")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_chat.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite**

Run: `cd src/app && python -m pytest -q`
Expected: PASS (all tests from Tasks 1–8).

- [ ] **Step 6: Commit**

```bash
git add src/app/main.py src/app/tests/test_chat.py
git commit -m "feat(chat): conversation-aware /api/chat with tool-call loop + router"
```

---

## Task 9: Integrations admin page (`integrations.html`)

**Files:**
- Create: `src/app/static/integrations.html`
- Test: `src/app/tests/test_static.py`

**Interfaces:**
- Consumes: the JSON API from Task 7 (`/api/integrations*`).
- Produces: a static page (registry list + Add modal + persist panel). No new Python interface.

This page is validated by (a) a smoke test that the route serves it, and (b) the manual verification steps below (run the app). It implements the approved Option-A layout, the modal (Source → Connection & auth → Operations), and the persist panel.

- [ ] **Step 1: Write the failing smoke test**

Create `src/app/tests/test_static.py`:
```python
import os
from fastapi.testclient import TestClient
import importlib


def test_integrations_page_served(monkeypatch, tmp_path):
    monkeypatch.setenv("INTEGRATIONS_CONFIG", str(tmp_path / "none.yaml"))
    import main
    importlib.reload(main)
    r = TestClient(main.app).get("/integrations")
    assert r.status_code == 200
    assert "Integrations" in r.text
    assert "Add integration" in r.text


def test_integrations_file_exists():
    assert os.path.isfile(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "integrations.html"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/app && python -m pytest tests/test_static.py -q`
Expected: FAIL — file/route missing.

- [ ] **Step 3: Create the page**

Create `src/app/static/integrations.html` (vanilla, matches `index.html` theme; calls the API):
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Integrations · BYOC Agent Starter</title>
  <style>
    :root { --bg:#0d1117; --panel:#161b22; --line:#30363d; --text:#e6edf3; --muted:#8b949e; --accent:#2f81f7; --ok:#3fb950; --warn:#d29922; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--text); }
    header { padding:14px 20px; border-bottom:1px solid var(--line); display:flex; align-items:center; gap:16px; }
    header h1 { font-size:15px; margin:0; font-weight:600; }
    nav a { font-size:13px; color:var(--muted); text-decoration:none; margin-right:12px; }
    nav a.on { color:var(--text); border-bottom:2px solid var(--accent); padding-bottom:11px; }
    main { max-width:760px; margin:0 auto; padding:24px 20px; }
    .toolbar { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; }
    .meta { color:var(--muted); font-size:13px; }
    button { background:var(--accent); color:#fff; border:0; border-radius:7px; padding:8px 14px; font-size:13px; font-weight:600; cursor:pointer; }
    button.ghost { background:var(--panel); border:1px solid var(--line); color:var(--text); }
    .row { display:flex; align-items:center; gap:12px; padding:12px 14px; border:1px solid var(--line); border-radius:9px; background:var(--panel); margin-bottom:10px; }
    .dot { width:9px; height:9px; border-radius:50%; background:var(--ok); flex:none; }
    .dot.off { background:var(--muted); }
    .nm { font-weight:600; } .badge { font-size:11px; color:var(--muted); border:1px solid var(--line); border-radius:10px; padding:1px 8px; margin-left:6px; }
    .sub { color:var(--muted); font-size:12px; }
    .grow { flex:1; }
    .pill { font-size:11px; color:var(--warn); border:1px solid #d2992244; border-radius:10px; padding:1px 8px; }
    .empty { color:var(--muted); text-align:center; padding:40px 0; }
    .overlay { position:fixed; inset:0; background:#010409cc; display:none; align-items:flex-start; justify-content:center; overflow:auto; padding:40px 16px; }
    .overlay.show { display:flex; }
    .modal { width:520px; max-width:100%; background:var(--panel); border:1px solid var(--line); border-radius:11px; }
    .m-h { display:flex; justify-content:space-between; align-items:center; padding:14px 16px; border-bottom:1px solid var(--line); }
    .m-b { padding:16px; } .sec { margin-bottom:18px; }
    .sec-t { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); border-bottom:1px solid #21262d; padding-bottom:6px; margin-bottom:10px; }
    label { display:block; font-size:12px; color:var(--muted); margin:8px 0 4px; }
    input, select, textarea { width:100%; background:var(--bg); border:1px solid var(--line); color:var(--text); border-radius:6px; padding:7px 9px; font-size:13px; font-family:inherit; }
    textarea { min-height:80px; }
    .ok { color:var(--ok); font-size:12px; } .err { color:#ffb4b4; font-size:12px; }
    .ops { max-height:200px; overflow:auto; border:1px solid var(--line); border-radius:6px; padding:8px; }
    .op { display:flex; gap:8px; align-items:center; font-size:12px; padding:3px 0; }
    .m-f { border-top:1px solid var(--line); padding:12px 16px; display:flex; justify-content:flex-end; gap:8px; }
    pre { background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:10px; font-size:11px; overflow:auto; white-space:pre; }
    .row-actions { display:flex; gap:8px; align-items:center; }
    .toggle { cursor:pointer; font-size:12px; color:var(--muted); }
  </style>
</head>
<body>
  <header>
    <h1>BYOC Agent Starter</h1>
    <nav><a href="/">Chat</a><a href="/integrations" class="on">Integrations</a></nav>
  </header>
  <main>
    <div class="toolbar">
      <span class="meta" id="meta">Loading…</span>
      <button id="add">+ Add integration</button>
    </div>
    <div id="list"></div>
  </main>

  <div class="overlay" id="overlay">
    <div class="modal">
      <div class="m-h"><b id="m-title">Add integration</b><span class="toggle" id="m-close">✕</span></div>
      <div class="m-b">
        <div class="sec">
          <div class="sec-t">1 · Source</div>
          <label>Name</label><input id="f-name" placeholder="Inventory API" />
          <label>OpenAPI spec URL (in-VPC)</label>
          <input id="f-spec-url" placeholder="http://inventory.svc.internal/v1/openapi.json" />
          <label>…or paste spec (JSON/YAML)</label><textarea id="f-spec-text"></textarea>
          <div style="margin-top:8px;"><button class="ghost" id="f-parse">Fetch &amp; parse</button>
            <span id="parse-status"></span></div>
        </div>
        <div class="sec" id="sec-conn" style="display:none;">
          <div class="sec-t">2 · Connection &amp; auth</div>
          <label>Base URL</label><input id="f-base" />
          <label>Auth type</label>
          <select id="f-auth"><option value="none">None</option>
            <option value="bearer">Bearer token</option>
            <option value="api_key_header">API key header</option></select>
          <div id="auth-header-wrap" style="display:none;"><label>Header name</label>
            <input id="f-header" placeholder="X-API-Key" /></div>
          <div id="auth-secret-wrap" style="display:none;"><label>Secret value 🔒 (stored in K8s Secret, never returned)</label>
            <input id="f-secret" type="password" /></div>
          <div style="margin-top:8px;"><button class="ghost" id="f-test">Test connection</button>
            <span id="test-status"></span></div>
        </div>
        <div class="sec" id="sec-ops" style="display:none;">
          <div class="sec-t">3 · Operations → tools <span id="ops-count" style="float:right;text-transform:none;"></span></div>
          <div class="sub" style="margin-bottom:6px;">Pick which operations the agent may call. Small models do best with ≤ ~8.</div>
          <div class="ops" id="ops"></div>
        </div>
        <div id="persist" style="display:none;">
          <div class="sec-t">Persist this</div>
          <p class="sub">Added <b>live now</b>. The app doesn't write to your cluster — apply this to persist, or commit it to your Nuon app and <code>nuon sync</code>.</p>
          <pre id="cm-yaml"></pre><pre id="sec-yaml"></pre>
        </div>
      </div>
      <div class="m-f">
        <button class="ghost" id="m-cancel">Close</button>
        <button id="f-save" style="display:none;">Save integration</button>
      </div>
    </div>
  </div>

<script>
const $ = (id) => document.getElementById(id);
let parsedOps = [];

async function load() {
  const res = await fetch('/api/integrations');
  const items = await res.json();
  const toolCount = items.reduce((n, i) => n + (i.tool_count || 0), 0);
  $('meta').textContent = `${items.length} integration(s) · ${toolCount} tools enabled · all in-VPC`;
  const list = $('list');
  list.innerHTML = items.length ? '' : '<div class="empty">No integrations yet. Everything stays in-boundary.</div>';
  for (const i of items) {
    const el = document.createElement('div');
    el.className = 'row';
    el.innerHTML = `<span class="dot ${i.enabled ? '' : 'off'}"></span>
      <div><div class="nm">${i.name}<span class="badge">${i.type}</span></div>
      <div class="sub">${i.base_url} · ${i.tool_count} tools · ${i.auth_type}</div></div>
      <span class="grow"></span>
      ${i.source === 'session' ? '<span class="pill">not persisted</span>' : ''}
      <div class="row-actions">
        <span class="toggle" data-id="${i.id}" data-enabled="${i.enabled}">${i.enabled ? 'Disable' : 'Enable'}</span>
        ${i.source === 'session' ? `<span class="toggle" data-del="${i.id}">Remove</span>` : ''}
      </div>`;
    list.appendChild(el);
  }
  list.querySelectorAll('[data-id]').forEach(s => s.onclick = async () => {
    await fetch('/api/integrations/' + s.dataset.id, {method:'PATCH',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({enabled: s.dataset.enabled !== 'true'})});
    load();
  });
  list.querySelectorAll('[data-del]').forEach(s => s.onclick = async () => {
    await fetch('/api/integrations/' + s.dataset.del, {method:'DELETE'}); load();
  });
}

function openModal() { $('overlay').classList.add('show'); }
function closeModal() { $('overlay').classList.remove('show'); resetModal(); }
function resetModal() {
  ['f-name','f-spec-url','f-spec-text','f-base','f-header','f-secret'].forEach(i => $(i).value='');
  ['sec-conn','sec-ops','persist','f-save'].forEach(i => $(i).style.display='none');
  $('parse-status').textContent=''; $('test-status').textContent=''; parsedOps=[];
}

$('add').onclick = () => { resetModal(); openModal(); };
$('m-close').onclick = closeModal; $('m-cancel').onclick = closeModal;
$('f-auth').onchange = () => {
  const t = $('f-auth').value;
  $('auth-header-wrap').style.display = t === 'api_key_header' ? 'block' : 'none';
  $('auth-secret-wrap').style.display = t === 'none' ? 'none' : 'block';
};

$('f-parse').onclick = async () => {
  $('parse-status').textContent = 'parsing…';
  const body = $('f-spec-text').value.trim()
    ? {spec_text: $('f-spec-text').value} : {spec_url: $('f-spec-url').value};
  const res = await fetch('/api/integrations/parse', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (!res.ok) { $('parse-status').innerHTML = '<span class="err">'+(await res.json()).detail+'</span>'; return; }
  const data = await res.json();
  parsedOps = data.operations;
  if (!$('f-name').value) $('f-name').value = data.title;
  $('f-base').value = data.server || '';
  $('parse-status').innerHTML = '<span class="ok">✓ '+parsedOps.length+' operations</span>';
  const ops = $('ops'); ops.innerHTML='';
  parsedOps.forEach((o,n) => {
    ops.innerHTML += `<label class="op"><input type="checkbox" data-op="${n}" style="width:auto;"/>
      <b>${o.method.toUpperCase()}</b> ${o.path} <span class="sub">${o.summary||''}</span></label>`;
  });
  ops.onchange = () => { const c = ops.querySelectorAll(':checked').length;
    $('ops-count').textContent = c + ' selected'; };
  ['sec-conn','sec-ops','f-save'].forEach(i => $(i).style.display = i==='f-save'?'inline-block':'block');
};

$('f-test').onclick = async () => {
  $('test-status').textContent = 'testing…';
  const res = await fetch('/api/integrations/test', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({
      base_url: $('f-base').value,
      auth: {type:$('f-auth').value, header:$('f-header').value},
      secret_value: $('f-secret').value})});
  const d = await res.json();
  $('test-status').innerHTML = d.ok ? '<span class="ok">✓ '+d.detail+'</span>'
    : '<span class="err">'+d.detail+' (you can still save)</span>';
};

$('f-save').onclick = async () => {
  const chosen = [...$('ops').querySelectorAll(':checked')].map(c => parsedOps[c.dataset.op]);
  const authType = $('f-auth').value;
  const slug = $('f-name').value.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/(^-|-$)/g,'');
  const auth = {type: authType};
  if (authType === 'api_key_header') auth.header = $('f-header').value;
  if (authType !== 'none') auth.secret_ref = slug + '-secret';
  const res = await fetch('/api/integrations', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({
      name: $('f-name').value, base_url: $('f-base').value, auth,
      secret_value: authType !== 'none' ? $('f-secret').value : null,
      operations: chosen})});
  const data = await res.json();
  $('cm-yaml').textContent = data.manifest.configmap_yaml;
  $('sec-yaml').textContent = data.manifest.secret_yaml || '# (no secret for this integration)';
  $('persist').style.display = 'block'; $('f-save').style.display='none';
  load();
};

load();
</script>
</body>
</html>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/app && python -m pytest tests/test_static.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Manual verification (real app, no Ollama needed for the UI)**

```bash
cd src/app && pip install -r requirements.txt -r requirements-dev.txt
INTEGRATIONS_CONFIG=/tmp/none.yaml python -m uvicorn main:app --port 8080
```
Open `http://localhost:8080/integrations`. Confirm: empty state shows; **+ Add integration** opens the modal; pasting a spec into the textarea + **Fetch & parse** lists operations; selecting ops + **Save** renders the ConfigMap/Secret YAML and the row appears with a "not persisted" pill; Disable/Enable and Remove work.

- [ ] **Step 6: Commit**

```bash
git add src/app/static/integrations.html src/app/tests/test_static.py
git commit -m "feat(ui): integrations admin page (registry + modal + persist panel)"
```

---

## Task 10: Chat page — localStorage history, Clear chat, nav link

**Files:**
- Modify: `src/app/static/index.html`

**Interfaces:**
- Consumes: `/api/chat` new `{messages:[...]}` shape (Task 8).
- Produces: no Python interface; client-side conversation persistence.

- [ ] **Step 1: Update the chat page**

In `src/app/static/index.html`, make these changes:

(a) Add a nav link + Clear button to the header. Replace the `<header>…</header>` block with:
```html
  <header>
    <h1>BYOC Agent Starter</h1>
    <span id="meta">self-hosted &middot; no frontier API calls</span>
    <span style="flex:1"></span>
    <a href="/integrations" style="font-size:13px;color:#8b949e;text-decoration:none;">Integrations →</a>
    <button id="clear" type="button" style="background:#161b22;border:1px solid #30363d;color:#8b949e;border-radius:7px;padding:6px 10px;font-size:12px;cursor:pointer;">Clear</button>
  </header>
```
And add `align-items:center;` to the existing `header { … }` rule (replace `align-items:baseline;` with `align-items:center;`).

(b) Replace the entire `<script>…</script>` block with:
```html
  <script>
    const log = document.getElementById('log');
    const form = document.getElementById('form');
    const input = document.getElementById('input');
    const send = document.getElementById('send');
    const KEY = 'byoc-chat-history';
    let history = JSON.parse(localStorage.getItem(KEY) || '[]');  // [{role,content}]

    fetch('/health').then(r => r.json()).then(d => {
      document.getElementById('meta').textContent =
        'self-hosted · model: ' + d.model + ' · ' + d.tools + ' tools · no frontier API calls';
    }).catch(() => {});

    function add(text, cls) {
      const el = document.createElement('div');
      el.className = 'msg ' + cls; el.textContent = text;
      log.appendChild(el); log.scrollTop = log.scrollHeight; return el;
    }
    function save() { localStorage.setItem(KEY, JSON.stringify(history)); }
    function render() {
      log.innerHTML = '';
      if (!history.length) add("Hi! I'm running on a self-hosted open-weight model inside this cluster. Ask me anything.", 'bot');
      for (const m of history) add(m.content, m.role === 'user' ? 'user' : 'bot');
    }
    document.getElementById('clear').onclick = () => { history = []; save(); render(); };
    render();

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const message = input.value.trim();
      if (!message) return;
      history.push({role:'user', content:message}); save(); add(message, 'user');
      input.value = ''; send.disabled = true;
      const thinking = add('…', 'bot');
      try {
        const res = await fetch('/api/chat', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({messages: history})
        });
        const data = await res.json();
        if (res.ok) {
          thinking.textContent = data.reply;
          history.push({role:'assistant', content:data.reply}); save();
        } else {
          thinking.remove();
          add(data.error || 'Something went wrong. If this is the first request, the model may still be warming up — try again in a minute.', 'err');
        }
      } catch (err) { thinking.remove(); add('Network error: ' + err, 'err'); }
      finally { send.disabled = false; input.focus(); }
    });
  </script>
```

- [ ] **Step 2: Manual verification**

Run the app (as in Task 9 Step 5). Send a message, reload the page → the conversation is still there. Click **Clear** → it empties. Confirm header shows the tools count and an "Integrations →" link.

- [ ] **Step 3: Commit**

```bash
git add src/app/static/index.html
git commit -m "feat(ui): persist chat history in localStorage + clear + nav link"
```

---

## Task 11: Helm chart — ConfigMap/Secret templates, mounts, values

**Files:**
- Create: `src/charts/chatbot/templates/configmap-integrations.yaml`
- Create: `src/charts/chatbot/templates/secret-integrations.yaml`
- Modify: `src/charts/chatbot/templates/deployment.yaml`
- Modify: `src/charts/chatbot/values.yaml`, `components/values/chatbot.yaml`

**Interfaces:**
- Produces: a `chatbot-integrations` ConfigMap + `chatbot-integration-secrets` Secret mounted into the pod, and env vars the app reads.

- [ ] **Step 1: Create the ConfigMap template**

Create `src/charts/chatbot/templates/configmap-integrations.yaml`:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: chatbot-integrations
  namespace: {{ .Values.namespace | default .Release.Namespace | quote }}
data:
  integrations.yaml: |
{{ .Values.integrations.yaml | default "integrations: []" | indent 4 }}
```

- [ ] **Step 2: Create the Secret template**

Create `src/charts/chatbot/templates/secret-integrations.yaml`:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: chatbot-integration-secrets
  namespace: {{ .Values.namespace | default .Release.Namespace | quote }}
type: Opaque
stringData:
{{ toYaml (.Values.integrationSecrets | default dict) | indent 2 }}
```

- [ ] **Step 3: Mount them + add env in the Deployment**

In `src/charts/chatbot/templates/deployment.yaml`, add to the `env:` list (after the `MODEL` block):
```yaml
        - name: INTEGRATIONS_CONFIG
          value: "/etc/chatbot/config/integrations.yaml"
        - name: INTEGRATIONS_SECRETS_DIR
          value: "/etc/chatbot/secrets"
        - name: ENABLE_INTEGRATIONS_ADMIN
          value: "{{ .Values.enableIntegrationsAdmin | default true }}"
```
Add a `volumeMounts:` block to the container (sibling of `env:`/`ports:`):
```yaml
        volumeMounts:
        - name: integrations-config
          mountPath: /etc/chatbot/config
        - name: integration-secrets
          mountPath: /etc/chatbot/secrets
          readOnly: true
```
Add a `volumes:` block to the pod spec (sibling of `containers:`):
```yaml
      volumes:
      - name: integrations-config
        configMap:
          name: chatbot-integrations
      - name: integration-secrets
        secret:
          secretName: chatbot-integration-secrets
```

- [ ] **Step 4: Add values defaults**

Append to `src/charts/chatbot/values.yaml`:
```yaml
enableIntegrationsAdmin: true

# Integration defs rendered into the chatbot-integrations ConfigMap.
# Empty in Tier 0. The /integrations UI generates this block for you.
integrations:
  yaml: |
    integrations: []

# Auth secret values, by secret_ref key. Empty in Tier 0.
integrationSecrets: {}
```
Append the same `enableIntegrationsAdmin`, `integrations`, and `integrationSecrets` keys to `components/values/chatbot.yaml` (so the Nuon-rendered values carry them).

- [ ] **Step 5: Verify the chart renders**

Run: `helm template src/charts/chatbot | grep -E "chatbot-integrations|INTEGRATIONS_CONFIG|chatbot-integration-secrets"`
Expected: the ConfigMap, the Secret, and the env var all appear. (If `helm` is unavailable, run `helm lint src/charts/chatbot` on a machine that has it, or visually confirm the templates.)

- [ ] **Step 6: Commit**

```bash
git add src/charts/chatbot/ components/values/chatbot.yaml
git commit -m "feat(helm): mount integrations ConfigMap+Secret and admin env"
```

---

## Task 12: Documentation updates

**Files:**
- Modify: `src/app/integrations/README.md`
- Modify: top-level `README.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Update the integrations README**

Replace `src/app/integrations/README.md` content so it reflects reality: the UI now exists at `/integrations`; the **OpenAPI path is working end-to-end** (parse → curate operations → server-side secret → live activation → emit ConfigMap/Secret YAML to persist); **MCP remains a stub** ("coming next"). Document: the env vars (`INTEGRATIONS_CONFIG`, `INTEGRATIONS_SECRETS_DIR`, `ENABLE_INTEGRATIONS_ADMIN`); that the app never writes to the cluster; that secrets stay in the K8s Secret and never reach the browser; the **dispatch heuristic** limitation; and the **security note** (Tier 0 has no app auth — front `/integrations` with ingress/auth and network-restrict it in production; spec/base URLs are fetched server-side).

- [ ] **Step 2: Update the top-level README**

In `README.md`, update the **"The integration scaffold"** section and the Tier-1 row of the complexity table: Tier 1 is now **add integrations via the `/integrations` UI** (OpenAPI working; MCP next), not "edit Python". Keep the framing that Tier 0 ships empty.

- [ ] **Step 3: Run the full test suite one more time**

Run: `cd src/app && python -m pytest -q`
Expected: PASS (all tests).

- [ ] **Step 4: Commit**

```bash
git add src/app/integrations/README.md README.md
git commit -m "docs: integrations UI exists (OpenAPI working, MCP next)"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** §4 modules → Tasks 1–8; §5 API → Task 7; §6 data flow → Tasks 7+8; §7 secret handling → Tasks 4/6/7 (in-memory secret, never returned, emitted once); §8 chat state → Tasks 8+10; §9 error handling → Tasks 2/5/7/8 (400 on bad spec, dispatch returns errors, 503 on model down); §10 security (admin gate) → Task 8 (`ENABLE_INTEGRATIONS_ADMIN`) + Task 12 (documented); §11 Helm → Task 11; §12 testing → every task; §13 file list → covered; MCP stays stub (untouched). **No gaps.**

**Placeholder scan:** no TBD/TODO; every code step has complete code; every command has expected output. Clear.

**Type consistency:** `Registry` methods (`tools`, `tool_index`, `secret_for`, `add_session`, `set_enabled`, `remove`) match between Tasks 4, 7, 8. `dispatch(integration, op, args, secret, client=None)` signature matches Task 5 and its call in Task 8. `render_manifest(integrations, secrets, …)` matches Task 6 and Task 7's `_manifest`. `parse_spec`/`operation_to_tool`/`tools_for` match Tasks 2/4/7. `Integration.to_def_dict`/`from_dict` match Tasks 1/3/6. Consistent.
