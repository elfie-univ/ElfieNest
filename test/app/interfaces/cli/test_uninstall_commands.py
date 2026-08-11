from pathlib import Path

from app.interfaces.cli import uninstall_commands


class _Uninstall:
    def __init__(self, home: Path) -> None:
        self.home = home

    def delete_local_config(self) -> bool:
        import shutil

        shutil.rmtree(self.home / "configs")
        return True


def test_delete_config_removes_only_final_config_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # Given: final configuration files and unrelated product data.
    configs = tmp_path / "configs"
    configs.mkdir()
    runtime_config = configs / "runtime.yaml"
    auth_env = configs / "auth.env"
    database = tmp_path / "nest.db"
    runtime_config.write_text("runtime", encoding="utf-8")
    auth_env.write_text("secret", encoding="utf-8")
    database.write_text("database", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

    # When: the config-only uninstall action runs.
    result = uninstall_commands._delete_config(_Uninstall(tmp_path), tmp_path)  # type: ignore[arg-type]

    # Then: final configs are removed while databases remain untouched.
    assert result == 0
    assert not runtime_config.exists()
    assert not auth_env.exists()
    assert database.read_text(encoding="utf-8") == "database"
