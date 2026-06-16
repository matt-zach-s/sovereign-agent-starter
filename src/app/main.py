import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI

# --- The swap layer ---------------------------------------------------------
# This is the whole "swap a frontier API for a self-hosted LLM" trick: the app
# uses the *standard* OpenAI client, just pointed at a self-hosted,
# OpenAI-compatible endpoint (Ollama) via OPENAI_BASE_URL. To migrate an
# existing OpenAI-based app, you change OPENAI_BASE_URL and nothing else.
# No frontier API calls ever leave the cluster.
BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.environ.get("OPENAI_API_KEY", "ollama")  # ignored by Ollama
MODEL = os.environ.get("MODEL", "llama3.2:3b")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# --- Integration scaffold (Tier 1, abstract) --------------------------------
# Fork this app and register your own tools to turn the chatbot into an agent
# that acts on your internal systems. Two supported extension points:
#   - OpenAPI specs -> integrations/openapi_tools.py
#   - MCP servers   -> integrations/mcp_tools.py
# Because the model is self-hosted and these point at services inside the
# customer's own VPC, data and credentials never leave the boundary.
# Tier 0 ships with NO tools registered (pure chat). See integrations/README.md.
from integrations.openapi_tools import load_openapi_tools
from integrations.mcp_tools import load_mcp_tools

TOOLS = load_openapi_tools() + load_mcp_tools()  # empty by default

app = FastAPI(title="BYOC Agent Starter — chatbot")


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "base_url": BASE_URL, "tools": len(TOOLS)}


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/api/chat")
def chat(req: ChatRequest):
    kwargs = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant running fully self-hosted, inside the customer's own cloud."},
            {"role": "user", "content": req.message},
        ],
    }
    if TOOLS:
        # Tier 1+: let the model call your registered internal-system tools.
        kwargs["tools"] = TOOLS
    try:
        resp = client.chat.completions.create(**kwargs)
        return {"reply": resp.choices[0].message.content}
    except Exception as e:
        # Most common at first boot: the model is still being pulled. Surface it.
        return JSONResponse(
            status_code=503,
            content={"error": f"model not ready or unreachable: {e}"},
        )
