from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import init_db

from ._helpers import create_test_owner


def _client(tmp_path: Path):
    db_path = str(tmp_path / "nest.db")
    config_path = tmp_path / "config.yaml"
    init_db(db_path)
    create_test_owner(db_path)
    patches = (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
        patch("elfienest.api.tool_owner_routes.get_config_path", return_value=config_path),
        patch("elfienest.api.tool_owner_routes.set_tool_secret"),
    )
    return db_path, config_path, patches


def test_tool_config_round_trip_uses_runtime_policy_and_local_secret(tmp_path):
    db_path, config_path, patches = _client(tmp_path)
    with patches[0], patches[1], patches[2], patches[3] as secret_writer:
        app = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                data={"username": "owner", "password": "ownerchangeme"},
            )
            headers = {"X-CSRF-Token": login.headers["X-CSRF-Token"]}
            initial = client.get("/api/owner/runtime/tools/", headers=headers)
            saved = client.put(
                "/api/owner/runtime/tools/web_search",
                json={
                    "enabled": True,
                    "provider": "brave",
                    "api_key": "local-only-key",
                    "max_results": 5,
                },
                headers=headers,
            )

    assert initial.status_code == 200
    assert initial.json()["tools"]["local_file"]["enabled"] is True
    assert saved.status_code == 200
    assert saved.json()["config"]["provider"] == "brave"
    secret_writer.assert_called_once_with("web_search", "local-only-key")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["runtime_policy"]["tools"]["web_search"]["provider"] == "brave"
    assert "local-only-key" not in config_path.read_text(encoding="utf-8")
