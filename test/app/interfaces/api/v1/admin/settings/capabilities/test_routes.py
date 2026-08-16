from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    CapabilitiesService,
    StoredValidationResult,
)
from app.interfaces.api.v1.admin.settings.capabilities import router
from app.interfaces.api.v1.auth import require_user
from infrastructure.persistence.configuration.bundled_defaults import load_tool_defaults
from infrastructure.persistence.configuration.capabilities import (
    RuntimeCapabilitiesAdapter,
)
from infrastructure.persistence.configuration.secrets import (
    resolve_secret,
    set_tool_secret,
)
from infrastructure.tools import ToolCapabilitySecretAdapter


class PassingValidator:
    def verify(self, capability_key):
        return StoredValidationResult(
            check_id=f"tool.{capability_key}",
            status="passed",
            message="validation passed",
            duration_ms=2.5,
            provider=None,
            model=None,
            error_type=None,
        )


def _client(tmp_path: Path, role="owner") -> tuple[TestClient, Path, Path]:
    config_path = tmp_path / "tools.yaml"
    secret_path = tmp_path / "auth.env"
    app = FastAPI()
    app.state.capabilities = CapabilitiesService(
        RuntimeCapabilitiesAdapter(
            config_path,
            defaults=load_tool_defaults(),
        ),
        ToolCapabilitySecretAdapter(
            secret_path,
            resolve=resolve_secret,
            write=set_tool_secret,
        ),
        PassingValidator(),
    )
    app.dependency_overrides[require_user] = lambda: AccountPrincipal(
        1, "person", role, "chat"
    )
    app.include_router(router)
    return TestClient(app), config_path, secret_path


def test_list_is_a_strict_read_only_collection(tmp_path: Path):
    client, config_path, secret_path = _client(tmp_path)

    response = client.get("/api/v1/admin/settings/capabilities")

    assert response.status_code == 200
    assert set(response.json()["tools"]) == {"web_search", "local_file"}
    assert not config_path.exists()
    assert not secret_path.exists()


def test_update_web_search_preserves_secret_boundary_and_tool_document(tmp_path: Path):
    client, config_path, secret_path = _client(tmp_path)

    response = client.patch(
        "/api/v1/admin/settings/capabilities/web-search",
        json={
            "enabled": True,
            "provider": "brave",
            "api_key": "local-only-key",
            "max_results": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()["config"]["provider"] == "brave"
    assert response.json()["config"]["has_api_key"] is True
    assert "api_key" not in response.json()["config"]
    assert "local-only-key" not in config_path.read_text(encoding="utf-8")
    assert "local-only-key" in secret_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["tools"]["web_search"]["provider"] == "brave"


def test_update_local_file_accepts_only_existing_editable_fields(tmp_path: Path):
    client, _config_path, _secret_path = _client(tmp_path)

    response = client.patch(
        "/api/v1/admin/settings/capabilities/local-file",
        json={"enabled": True, "max_read_bytes": 32768},
    )
    rejected = client.patch(
        "/api/v1/admin/settings/capabilities/local-file",
        json={"root": "/tmp"},
    )

    assert response.status_code == 200
    assert response.json()["config"]["max_read_bytes"] == 32768
    assert response.json()["config"]["root_policy"] == "elfie_workspace"
    assert rejected.status_code == 422
    assert rejected.json() == {
        "error": {
            "code": "invalid_capability_configuration",
            "message": "能力配置请求无效",
            "details": {},
        }
    }


def test_member_gets_stable_forbidden_error_envelope(tmp_path: Path):
    client, _config_path, _secret_path = _client(tmp_path, "member")

    response = client.get("/api/v1/admin/settings/capabilities")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "capabilities_forbidden",
            "message": "只有家庭管理员可以管理系统能力",
            "details": {},
        }
    }


def test_verify_uses_existing_typed_suite_shape(tmp_path: Path):
    client, _config_path, _secret_path = _client(tmp_path)

    response = client.post("/api/v1/admin/settings/capabilities/local-file/verify")

    assert response.status_code == 200
    assert response.json()["name"] == "tool:local_file"
    assert response.json()["summary"] == {
        "passed": 1,
        "failed": 0,
        "warning": 0,
        "skipped": 0,
    }
    assert response.json()["results"][0]["details"] == {"error_type": None}
