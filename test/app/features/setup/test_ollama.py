from __future__ import annotations

import copy
from pathlib import Path

import pytest

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.store import FoodCatalogStore
from ai_runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from app.features.setup.ollama import OllamaSetupService
from app.features.setup.runtime_config import build_ollama_setup_service
from app.features.setup.service import (
    complete_setup_step,
    create_first_owner,
    get_setup_progress,
)
from app.infrastructure.ollama_platform import (
    OFFICIAL_INSTALL_URLS,
    DownloadedInstaller,
    OllamaBinding,
    OllamaPlatformAdapter,
    OllamaProbe,
)
from app.infrastructure.persistence.store import init_db


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class _HealthyAdapter:
    platform = "darwin"

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")


def _write_bound_config(root: Path) -> None:
    write_yaml_mapping(
        root / "config.yaml",
        {"providers": {"ollama": {"api_base": "http://127.0.0.1:11434"}}},
    )


def test_healthy_existing_ollama_binds_without_installer_or_endpoint_switch(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    config: dict[str, object] = {"providers": {}}
    writes: list[dict[str, object]] = []
    service = OllamaSetupService(
        adapter=_HealthyAdapter(),  # type: ignore[arg-type]
        read_config=lambda: config,
        write_config=writes.append,
    )

    probe = service.bind_existing(db_path=db_path, endpoint="http://127.0.0.1:11434")

    assert probe.state == "healthy"
    assert len(writes) == 1
    provider = writes[0]["providers"]["ollama"]  # type: ignore[index]
    assert provider["api_base"] == "http://127.0.0.1:11434"  # type: ignore[index]
    assert get_setup_progress(db_path).current_step == 3
    with pytest.raises(ValueError, match="已固定"):
        service.bind_existing(db_path=db_path, endpoint="http://127.0.0.1:22444")


def test_binding_rolls_back_config_when_setup_step_is_invalid(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    stored: dict[str, object] = {"providers": {}}
    original = copy.deepcopy(stored)

    def write_config(config: dict[str, object]) -> None:
        stored.clear()
        stored.update(copy.deepcopy(config))

    service = OllamaSetupService(
        adapter=_HealthyAdapter(),  # type: ignore[arg-type]
        read_config=lambda: copy.deepcopy(stored),
        write_config=write_config,
    )

    with pytest.raises(ValueError, match="第 1 步"):
        service.bind_existing(
            db_path=db_path,
            endpoint="http://127.0.0.1:11434",
        )

    assert stored == original


def test_runtime_builder_rollback_does_not_backup_rejected_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    original: dict[str, object] = {"providers": {}}
    write_yaml_mapping(tmp_path / "config.yaml", original)
    service = build_ollama_setup_service(
        db_path,
        adapter=_HealthyAdapter(),  # type: ignore[arg-type]
    )

    def reject_milestone(*_args: object, **_kwargs: object) -> None:
        raise ValueError("forced milestone rejection")

    monkeypatch.setattr(
        "app.features.setup.config_commit.complete_setup_step",
        reject_milestone,
    )
    with pytest.raises(ValueError, match="forced milestone rejection"):
        service.bind_existing(
            db_path=db_path,
            endpoint="http://127.0.0.1:11434",
        )

    assert read_yaml_mapping(tmp_path / "config.yaml") == original
    assert read_yaml_mapping(tmp_path / "config.yaml.bak") == original


def test_invalid_model_step_leaves_no_food_or_evidence_files(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    config: dict[str, object] = {
        "providers": {
            "ollama": {
                "api_base": "http://127.0.0.1:11434",
                "installation": {
                    "platform": "linux",
                    "install_kind": "existing-public",
                    "launch_target": "",
                    "version": "",
                },
            }
        }
    }
    foods_path = tmp_path / "foods.yaml"
    evidence_path = tmp_path / "models.yaml"
    service = OllamaSetupService(
        adapter=_ModelAdapter(),  # type: ignore[arg-type]
        read_config=lambda: copy.deepcopy(config),
        write_config=lambda updated: config.update(copy.deepcopy(updated)),
        food_catalog_store=FoodCatalogStore(foods_path, tmp_path / "food-history"),
        model_evidence_store=ModelEvidenceStore(evidence_path),
    )

    with pytest.raises(ValueError, match="第 2 步"):
        service.configure_installed_model(
            db_path=db_path,
            model_reference="ollama/qwen2.5:0.5b",
        )

    assert not foods_path.exists()
    assert not evidence_path.exists()


def test_adapter_reports_deleted_binding_without_scanning_another_endpoint() -> None:
    adapter = OllamaPlatformAdapter(
        platform_name="linux",
        request_opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")),
    )

    probe = adapter.probe(
        OllamaBinding(
            api_base="http://127.0.0.1:11434",
            platform="linux",
            install_kind="binary",
            launch_target="/missing/ollama",
            version="0.12.0",
        )
    )

    assert probe.state == "deleted"
    assert probe.endpoint == "http://127.0.0.1:11434"


def test_official_installer_is_downloaded_then_runs_only_the_fixed_template() -> None:
    commands: list[tuple[str, ...]] = []
    adapter = OllamaPlatformAdapter(
        platform_name="win32",
        request_opener=lambda *_args, **_kwargs: _Response(b"Write-Output official"),
        command_runner=lambda command, **_kwargs: (
            commands.append(tuple(command)) or _Completed(0)
        ),
    )

    installer = adapter.download_official_installer()
    with pytest.raises(PermissionError, match="用户确认"):
        adapter.run_confirmed_installer(installer, user_confirmed=False)
    assert commands == []

    adapter.run_confirmed_installer(installer, user_confirmed=True)

    assert installer.source_url == OFFICIAL_INSTALL_URLS["win32"]
    assert len(installer.sha256) == 64
    assert commands == [installer.command]


def test_official_binding_with_invalid_platform_signature_requires_repair(
    tmp_path: Path,
) -> None:
    application = tmp_path / "Ollama.app"
    application.mkdir()
    adapter = OllamaPlatformAdapter(
        platform_name="darwin",
        command_runner=lambda *_args, **_kwargs: _Completed(1),
    )
    binding = OllamaBinding(
        api_base="http://127.0.0.1:11434",
        platform="darwin",
        install_kind="official-script",
        launch_target=str(application),
        version="0.12.0",
        installer_source_url=OFFICIAL_INSTALL_URLS["darwin"],
        installer_sha256="a" * 64,
    )

    probe = adapter.probe(binding)

    assert probe.state == "repair_required"
    assert probe.endpoint == binding.api_base


def test_linux_official_binding_requires_recorded_script_provenance(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "ollama"
    executable.write_text("binary", encoding="utf-8")
    adapter = OllamaPlatformAdapter(
        platform_name="linux",
        request_opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")),
    )
    binding = OllamaBinding(
        api_base="http://127.0.0.1:11434",
        platform="linux",
        install_kind="official-script",
        launch_target=str(executable),
        version="0.12.0",
    )

    probe = adapter.probe(binding)

    assert probe.state == "repair_required"


def test_repair_starts_only_the_saved_public_ollama_binding(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    executable = tmp_path / "ollama"
    executable.write_text("binary", encoding="utf-8")
    config: dict[str, object] = {
        "providers": {
            "ollama": {
                "api_base": "http://127.0.0.1:11434",
                "installation": {
                    "api_base": "http://127.0.0.1:11434",
                    "platform": "linux",
                    "install_kind": "binary",
                    "launch_target": str(executable),
                    "version": "0.12.0",
                },
            }
        }
    }
    adapter = _RepairAdapter()
    service = OllamaSetupService(
        adapter=adapter,  # type: ignore[arg-type]
        read_config=lambda: config,
        write_config=lambda _config: None,
    )

    probe = service.repair_bound(db_path=db_path)

    assert probe.state == "healthy"
    assert adapter.started == [str(executable)]


def test_official_install_saves_one_verified_binding_only_after_confirmation(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    config: dict[str, object] = {"providers": {}}
    writes: list[dict[str, object]] = []
    adapter = _OfficialAdapter(tmp_path)
    service = OllamaSetupService(
        adapter=adapter,  # type: ignore[arg-type]
        read_config=lambda: config,
        write_config=writes.append,
    )

    probe = service.install_official(
        db_path=db_path,
        endpoint="http://127.0.0.1:11434",
        user_confirmed=True,
    )

    assert probe.state == "healthy"
    assert adapter.confirmations == [True]
    assert adapter.models_checked == ["http://127.0.0.1:11434"]
    assert len(writes) == 1
    installation = writes[0]["providers"]["ollama"]["installation"]  # type: ignore[index]
    assert installation["installer_source_url"] == OFFICIAL_INSTALL_URLS["linux"]  # type: ignore[index]
    assert get_setup_progress(db_path).current_step == 3


def test_configured_model_must_exist_on_the_one_saved_ollama_endpoint(
    tmp_path: Path,
) -> None:
    """模型选择保存完整引用，且不会靠另一个本地 endpoint 侥幸通过。"""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    _write_bound_config(tmp_path)
    complete_setup_step(
        db_path,
        step=2,
        decision="bound_existing",
        ollama_endpoint="http://127.0.0.1:11434",
    )
    complete_setup_step(db_path, step=3)
    config: dict[str, object] = {
        "providers": {
            "ollama": {
                "api_base": "http://127.0.0.1:11434",
                "installation": {
                    "platform": "linux",
                    "install_kind": "existing-public",
                    "launch_target": "",
                    "version": "",
                },
            }
        }
    }
    writes: list[dict[str, object]] = []
    service = OllamaSetupService(
        adapter=_ModelAdapter(),  # type: ignore[arg-type]
        read_config=lambda: config,
        write_config=writes.append,
        food_catalog_store=FoodCatalogStore(
            tmp_path / "foods.yaml", tmp_path / "food-history"
        ),
        model_evidence_store=ModelEvidenceStore(tmp_path / "models.yaml"),
    )

    service.configure_installed_model(
        db_path=db_path,
        model_reference="ollama/qwen2.5:0.5b",
    )

    assert writes[0]["providers"]["ollama"]["selected_model"] == "ollama/qwen2.5:0.5b"  # type: ignore[index]
    catalog = FoodCatalogStore(
        tmp_path / "foods.yaml", tmp_path / "food-history"
    ).load()
    assert catalog.recipes["standard"].primary.model == "ollama/qwen2.5:0.5b"
    assert get_setup_progress(db_path).current_step == 5


def test_runtime_builder_keeps_model_artifacts_beside_explicit_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit_root = tmp_path / "explicit"
    ambient_root = tmp_path / "ambient"
    explicit_root.mkdir()
    db_path = str(explicit_root / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    write_yaml_mapping(
        explicit_root / "config.yaml",
        {
            "providers": {
                "ollama": {
                    "api_base": "http://127.0.0.1:11434",
                    "installation": {
                        "platform": "linux",
                        "install_kind": "existing-public",
                        "launch_target": "",
                        "version": "",
                    },
                }
            }
        },
    )
    complete_setup_step(
        db_path,
        step=2,
        decision="bound_existing",
        ollama_endpoint="http://127.0.0.1:11434",
    )
    complete_setup_step(db_path, step=3)
    monkeypatch.setenv("ELFIE_HOME", str(ambient_root))
    service = build_ollama_setup_service(
        db_path,
        adapter=_ModelAdapter(),  # type: ignore[arg-type]
    )

    service.configure_installed_model(
        db_path=db_path,
        model_reference="ollama/qwen2.5:0.5b",
    )

    assert (explicit_root / "foods.yaml").is_file()
    assert (explicit_root / "model_evidence.yaml").is_file()
    assert not (ambient_root / "foods.yaml").exists()
    assert not (ambient_root / "model_evidence.yaml").exists()


def test_runtime_builder_removes_model_artifacts_when_milestone_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    write_yaml_mapping(
        tmp_path / "config.yaml",
        {
            "providers": {
                "ollama": {
                    "api_base": "http://127.0.0.1:11434",
                    "installation": {
                        "platform": "linux",
                        "install_kind": "existing-public",
                        "launch_target": "",
                        "version": "",
                    },
                }
            }
        },
    )
    complete_setup_step(
        db_path,
        step=2,
        decision="bound_existing",
        ollama_endpoint="http://127.0.0.1:11434",
    )
    complete_setup_step(db_path, step=3)
    service = build_ollama_setup_service(
        db_path,
        adapter=_ModelAdapter(),  # type: ignore[arg-type]
    )

    def reject_milestone(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("forced milestone rejection after side effects")

    monkeypatch.setattr(
        "app.features.setup.config_commit.complete_setup_step",
        reject_milestone,
    )
    with pytest.raises(RuntimeError, match="forced milestone rejection"):
        service.configure_installed_model(
            db_path=db_path,
            model_reference="ollama/qwen2.5:0.5b",
        )

    assert not (tmp_path / "foods.yaml").exists()
    assert not (tmp_path / "model_evidence.yaml").exists()
    assert not (tmp_path / "food_history").exists()
    config = read_yaml_mapping(tmp_path / "config.yaml")
    assert "selected_model" not in config["providers"]["ollama"]  # type: ignore[index]


def test_model_pull_rechecks_the_fixed_endpoint_before_configuring(
    tmp_path: Path,
) -> None:
    """模型拉取后必须再次在同一 endpoint 看到模型，才会写入配置。"""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, username="owner", password="secret123")
    _write_bound_config(tmp_path)
    complete_setup_step(
        db_path,
        step=2,
        decision="bound_existing",
        ollama_endpoint="http://127.0.0.1:11434",
    )
    complete_setup_step(db_path, step=3)
    config: dict[str, object] = {
        "providers": {
            "ollama": {
                "api_base": "http://127.0.0.1:11434",
                "installation": {
                    "platform": "linux",
                    "install_kind": "existing-public",
                    "launch_target": "",
                    "version": "",
                },
            }
        }
    }
    adapter = _PullAdapter()
    service = OllamaSetupService(
        adapter=adapter,  # type: ignore[arg-type]
        read_config=lambda: config,
        write_config=lambda _config: None,
        food_catalog_store=FoodCatalogStore(
            tmp_path / "foods.yaml", tmp_path / "food-history"
        ),
        model_evidence_store=ModelEvidenceStore(tmp_path / "models.yaml"),
    )

    service.pull_and_configure_model(
        db_path=db_path,
        model_reference="ollama/qwen2.5:0.5b",
    )

    assert adapter.pulled == [("http://127.0.0.1:11434", "qwen2.5:0.5b")]
    assert get_setup_progress(db_path).current_step == 5


class _ModelAdapter:
    platform = "linux"

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        assert binding.api_base == "http://127.0.0.1:11434"
        return ("qwen2.5:0.5b",)


class _PullAdapter(_ModelAdapter):
    def __init__(self) -> None:
        self.pulled: list[tuple[str, str]] = []

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        return () if not self.pulled else ("qwen2.5:0.5b",)

    def pull_model(self, binding: OllamaBinding, model_id: str) -> None:
        self.pulled.append((binding.api_base, model_id))


class _OfficialAdapter:
    platform = "linux"

    def __init__(self, directory: Path) -> None:
        self.confirmations: list[bool] = []
        self.models_checked: list[str] = []
        self.installer = DownloadedInstaller(
            source_url=OFFICIAL_INSTALL_URLS["linux"],
            sha256="a" * 64,
            script_path=directory / "official-install.sh",
            command=("/bin/sh", str(directory / "official-install.sh")),
        )

    def download_official_installer(self) -> DownloadedInstaller:
        return self.installer

    def run_confirmed_installer(
        self, _installer: DownloadedInstaller, *, user_confirmed: bool
    ) -> None:
        self.confirmations.append(user_confirmed)

    def official_binding_after_install(
        self, *, endpoint: str, installer: DownloadedInstaller
    ) -> OllamaBinding:
        return OllamaBinding(
            api_base=endpoint,
            platform="linux",
            install_kind="official-script",
            launch_target="/usr/local/bin/ollama",
            version="",
            installer_source_url=installer.source_url,
            installer_sha256=installer.sha256,
        )

    def start_bound_installation(self, _binding: OllamaBinding) -> None:
        return None

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        self.models_checked.append(binding.api_base)
        return ("qwen2.5:0.5b",)

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")


class _RepairAdapter:
    platform = "linux"

    def __init__(self) -> None:
        self.started: list[str] = []

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        state = "healthy" if self.started else "stopped"
        return OllamaProbe(state, binding.api_base, version="0.12.0")

    def start_bound_installation(self, binding: OllamaBinding) -> None:
        self.started.append(binding.launch_target)


class _Completed:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""
