"""Tier 1 extension point: turn an OpenAPI spec into agent tools.

This is intentionally a stub. Fork the starter kit and implement
``load_openapi_tools()`` to fetch your internal service's OpenAPI/Swagger spec
and convert each operation into an OpenAI-compatible tool definition. Because the
model is self-hosted and the spec points at services inside the customer's own
VPC, no data leaves the boundary.

Return a list of OpenAI tool definitions, e.g.::

    [{"type": "function",
      "function": {"name": "get_customer", "description": "...",
                   "parameters": {...json schema...}}}]

Then implement the dispatch side (calling the real endpoint when the model emits
a tool call) in main.py's chat handler.
"""
import os

# Comma-separated list of OpenAPI/Swagger spec URLs reachable inside the VPC.
OPENAPI_SPEC_URLS = [u for u in os.environ.get("OPENAPI_SPEC_URLS", "").split(",") if u]


def load_openapi_tools():
    # TODO (Tier 1): fetch each spec in OPENAPI_SPEC_URLS and map operations -> tools.
    return []
