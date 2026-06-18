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
