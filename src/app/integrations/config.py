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
