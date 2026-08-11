from pathlib import Path

from app.interfaces.cli import uninstall_commands


class _Uninstall:
    def __init__(self, home: Path) -> None:
        self.home = home

    def delete_local_config(self) -> bool:
        import shutil

        shutil.rmtree(self.home / "configs")
        return True


def test_delete_config_removes_credentials_but_keeps_product_data(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configs_dir = tmp_path / "configs"
    config_path = configs_dir / "runtime.yaml"
    provider_path = configs_dir / "providers.yaml"
    tool_path = configs_dir / "tools.yaml"
    food_path = configs_dir / "food-packages.yaml"
    credentials_dir = configs_dir / "credentials"
    api_keys_path = credentials_dir / "api-keys.env"
    oauth_path = credentials_dir / "oauth" / "openai.json"
    reports_dir = tmp_path / "reports"
    db_path = tmp_path / "nest.db"
    api_keys_path.parent.mkdir(parents=True)
    oauth_path.parent.mkdir(parents=True)
    config_path.write_text("providers: {}\n", encoding="utf-8")
    provider_path.write_text("providers: {}\n", encoding="utf-8")
    tool_path.write_text("tools: {}\n", encoding="utf-8")
    food_path.write_text("foods: {}\n", encoding="utf-8")
    api_keys_path.write_text("OPENAI_API_KEY=placeholder\n", encoding="utf-8")
    oauth_path.write_text('{"access_token":"placeholder"}\n', encoding="utf-8")
    reports_dir.mkdir()
    (reports_dir / "model-evidence.yaml").write_text(
        "models: {}\n",
        encoding="utf-8",
    )
    db_path.write_text("database-placeholder", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

    exit_code = uninstall_commands._delete_config(_Uninstall(tmp_path), tmp_path)  # type: ignore[arg-type]

    assert exit_code == 0
    assert not configs_dir.exists()
    assert reports_dir.exists()
    assert db_path.read_text(encoding="utf-8") == "database-placeholder"
