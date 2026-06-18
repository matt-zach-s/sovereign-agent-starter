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
