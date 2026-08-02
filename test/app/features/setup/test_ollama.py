from __future__ import annotations

from pathlib import Path

import pytest

from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID
from ai_runtime.food.store import FoodCatalogStore
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.report_repository import ReportRepository
from app.features.setup.ollama import OllamaSetupService
from app.features.setup.service import (
    complete_setup_step,
    create_first_owner,
    get_setup_progress,
)
from app.infrastructure.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OFFICIAL_INSTALL_URLS,
    DownloadedInstaller,
    OllamaBinding,
    OllamaProbe,
)
from app.infrastructure.persistence.store import init_db


def test_inspect_uses_the_fixed_local_endpoint_and_reports_installed_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup may inspect the documented local endpoint, but never scan arbitrary hosts."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    adapter = _InspectionAdapter()
    service = OllamaSetupService(
        adapter=adapter,  # type: ignore[arg-type]
    )

    observation = service.inspect()

    assert observation.probe.state == "healthy"
    assert observation.probe.endpoint == DEFAULT_OLLAMA_ENDPOINT
    assert observation.models == ("qwen2.5:3b",)
    assert [binding.api_base for binding in adapter.probed] == [DEFAULT_OLLAMA_ENDPOINT]


def test_repair_starts_only_the_saved_public_ollama_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, account_id="owner", password="secret123")
    executable = tmp_path / "ollama"
    executable.write_text("binary", encoding="utf-8")
    ProviderConnectionStore().create(
        catalog_id="ollama",
        alias="Ollama",
        api_base="http://127.0.0.1:11434",
        api_mode="ollama",
        auth_type="none",
        installation={
            "platform": "linux",
            "install_kind": "binary",
            "launch_target": str(executable),
            "version": "0.12.0",
        },
    )
    adapter = _RepairAdapter()
    service = OllamaSetupService(
        adapter=adapter,  # type: ignore[arg-type]
    )

    probe = service.repair_bound(db_path=db_path)

    assert probe.state == "healthy"
    assert adapter.started == [str(executable)]


def test_official_install_saves_one_verified_binding_only_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, account_id="owner", password="secret123")
    adapter = _OfficialAdapter(tmp_path)
    service = OllamaSetupService(
        adapter=adapter,  # type: ignore[arg-type]
    )

    probe = service.install_official(
        db_path=db_path,
        endpoint="http://127.0.0.1:11434",
        user_confirmed=True,
    )

    assert probe.state == "healthy"
    assert adapter.confirmations == [True]
    assert adapter.models_checked == ["http://127.0.0.1:11434"]
    connection = next(iter(ProviderConnectionStore().load().connections.values()))
    assert (
        connection.installation["installer_source_url"]
        == OFFICIAL_INSTALL_URLS["linux"]
    )
    assert get_setup_progress(db_path).current_step == 3


def test_configured_model_must_exist_on_the_one_saved_ollama_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    """模型选择保存完整引用，且不会靠另一个本地 endpoint 侥幸通过。"""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, account_id="owner", password="secret123")
    complete_setup_step(
        db_path,
        step=2,
        decision="bound_existing",
        ollama_endpoint="http://127.0.0.1:11434",
    )
    complete_setup_step(db_path, step=3)
    ProviderConnectionStore().create(
        catalog_id="ollama",
        alias="Ollama",
        api_base="http://127.0.0.1:11434",
        api_mode="ollama",
        auth_type="none",
        installation={
            "platform": "linux",
            "install_kind": "existing-public",
            "launch_target": "",
            "version": "",
        },
    )
    service = OllamaSetupService(
        adapter=_ModelAdapter(),  # type: ignore[arg-type]
        food_catalog_store=FoodCatalogStore(
            tmp_path / "foods.yaml", tmp_path / "food-history"
        ),
        report_repository=ReportRepository(tmp_path / "reports.db"),
    )

    service.configure_installed_model(
        db_path=db_path,
        model_reference="ollama/qwen2.5:0.5b",
    )

    connection = ProviderConnectionStore().load().connections["ollama_0001"]
    assert connection.models[0].endpoint_model_id == "qwen2.5:0.5b"
    catalog = FoodCatalogStore(
        tmp_path / "foods.yaml", tmp_path / "food-history"
    ).load()
    assert catalog.packages[FOOD_EMERGENCY_ID].primary.model == (
        "ollama_0001/qwen2.5:0.5b"
    )
    assert catalog.packages[FOOD_COMMON_ID].primary.model == (
        "ollama_0001/qwen2.5:0.5b"
    )
    assert get_setup_progress(db_path).current_step == 5


def test_model_pull_rechecks_the_fixed_endpoint_before_configuring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    """模型拉取后必须再次在同一 endpoint 看到模型，才会写入配置。"""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, account_id="owner", password="secret123")
    complete_setup_step(
        db_path,
        step=2,
        decision="bound_existing",
        ollama_endpoint="http://127.0.0.1:11434",
    )
    complete_setup_step(db_path, step=3)
    ProviderConnectionStore().create(
        catalog_id="ollama",
        alias="Ollama",
        api_base="http://127.0.0.1:11434",
        api_mode="ollama",
        auth_type="none",
        installation={
            "platform": "linux",
            "install_kind": "existing-public",
            "launch_target": "",
            "version": "",
        },
    )
    adapter = _PullAdapter()
    service = OllamaSetupService(
        adapter=adapter,  # type: ignore[arg-type]
        food_catalog_store=FoodCatalogStore(
            tmp_path / "foods.yaml", tmp_path / "food-history"
        ),
        report_repository=ReportRepository(tmp_path / "reports.db"),
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


class _InspectionAdapter:
    platform = "linux"

    def __init__(self) -> None:
        self.probed: list[OllamaBinding] = []

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        self.probed.append(binding)
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        assert binding.api_base == DEFAULT_OLLAMA_ENDPOINT
        return ("qwen2.5:3b",)


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
