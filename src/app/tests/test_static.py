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
