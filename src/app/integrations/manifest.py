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
