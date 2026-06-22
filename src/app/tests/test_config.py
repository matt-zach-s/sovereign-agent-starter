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
