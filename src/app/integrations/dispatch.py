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
