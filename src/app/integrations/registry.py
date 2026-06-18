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
