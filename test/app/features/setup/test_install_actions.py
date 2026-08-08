"""Real Setup phase actions: Ollama branches, model reuse/pull, food and beds."""

from __future__ import annotations

from pathlib import Path

from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.report_repository import ReportRepository
from app.features.setup.install_actions import run_setup_installation
from app.features.setup.service import create_first_owner_from_hash
from app.infrastructure.ollama_platform import (
    OFFICIAL_INSTALL_URLS,
    DownloadedInstaller,
    OllamaBinding,
    OllamaProbe,
)
from app.infrastructure.persistence.final_schema import create_final_nest_database
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import get_db


def _locked_draft(db_path: str, *, use_local: bool, model_id: str | None) -> None:
    drafts = SetupInstallRepository(db_path)
    drafts.save_owner_draft(
        account_id="owner",
        display_name="Owner",
        password_hash="pbkdf2_sha256$260000$salt$hash",
    )
    drafts.save_offline_draft(use_local_ollama=use_local, model_id=model_id)
    drafts.save_nest_draft(bed_count=8)
    draft = drafts.get_draft()
    create_first_owner_from_hash(db_path, draft)
    drafts.lock_draft()
    SetupInstallRepository(db_path).begin_or_resume()


def test_installation_without_local_ollama_skips_three_phases_and_applies_beds(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _locked_draft(db_path, use_local=False, model_id=None)

    run_setup_installation(db_path, adapter=_UnusedAdapter())

    record = SetupInstallRepository(db_path).get()
    assert record.task_status == "completed"
    with get_db(db_path) as connection:
        assert connection.execute(
            "SELECT bed_count FROM nest_settings WHERE nest_id='local'"
        ).fetchone()[0] == 8


def test_stopped_public_ollama_is_started_without_reinstall(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _locked_draft(db_path, use_local=True, model_id="qwen2.5:0.5b")
    ProviderConnectionStore().create(
        catalog_id="ollama",
        alias="Ollama",
        api_base="http://127.0.0.1:11434",
        api_mode="ollama",
        installation={
            "platform": "linux",
            "install_kind": "existing-public",
            "launch_target": "/usr/local/bin/ollama",
        },
    )
    adapter = _DelayedStartAdapter()
    run_setup_installation(db_path, adapter=adapter)

    assert adapter.started == ["/usr/local/bin/ollama"]
    assert adapter.installers == 0
    assert SetupInstallRepository(db_path).get().task_status == "completed"


def test_healthy_public_ollama_and_model_are_reused_without_install_or_pull(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _locked_draft(db_path, use_local=True, model_id="qwen2.5:0.5b")
    ProviderConnectionStore().create(
        catalog_id="ollama",
        alias="Ollama",
        api_base="http://127.0.0.1:11434",
        api_mode="ollama",
        auth_type="none",
        installation={
            "platform": "linux",
            "install_kind": "existing-public",
            "launch_target": "/usr/local/bin/ollama",
        },
    )
    adapter = _HealthyAdapter()

    run_setup_installation(db_path, adapter=adapter)

    assert adapter.installers == 0
    assert adapter.pulled == []
    assert adapter.started == []
    assert SetupInstallRepository(db_path).get().task_status == "completed"


def test_absent_ollama_is_installed_and_missing_model_is_pulled(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _locked_draft(db_path, use_local=True, model_id="qwen2.5:0.5b")
    adapter = _InstallingAdapter(tmp_path)

    run_setup_installation(db_path, adapter=adapter)

    assert adapter.installers == 1
    assert adapter.confirmations == [True]
    assert adapter.pulled == ["qwen2.5:0.5b"]
    assert SetupInstallRepository(db_path).get().task_status == "completed"


def test_failed_start_repairs_the_same_public_ollama_and_emergency_food_only(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _locked_draft(db_path, use_local=True, model_id="gemma3:270m")
    ProviderConnectionStore().create(
        catalog_id="ollama",
        alias="Ollama",
        api_base="http://127.0.0.1:11434",
        api_mode="ollama",
        installation={
            "platform": "linux",
            "install_kind": "existing-public",
            "launch_target": "/usr/local/bin/ollama",
        },
    )
    food_repository = SQLiteFoodPackageRepository(db_path)
    before_common = food_repository.get(FOOD_COMMON_ID)
    adapter = _RepairingAdapter(tmp_path)
    run_setup_installation(
        db_path,
        adapter=adapter,
        food_catalog_repository=food_repository,
        report_repository=ReportRepository(tmp_path / "reports.db"),
    )

    assert adapter.installers == 1
    catalog = food_repository.load()
    assert catalog.packages[FOOD_EMERGENCY_ID].primary is not None
    assert catalog.packages[FOOD_EMERGENCY_ID].primary.model.endswith("/gemma3:270m")
    assert catalog.packages[FOOD_COMMON_ID] == before_common


class _UnusedAdapter:
    platform = "linux"


class _StartAdapter:
    platform = "linux"

    def __init__(self) -> None:
        self.started: list[str] = []
        self.installers = 0

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        return OllamaProbe(
            "healthy" if self.started else "stopped",
            binding.api_base,
            version="0.12.0",
        )

    def start_bound_installation(self, binding: OllamaBinding) -> None:
        self.started.append(binding.launch_target)

    def list_models(self, _binding: OllamaBinding) -> tuple[str, ...]:
        return ("qwen2.5:0.5b", "gemma3:270m")


class _DelayedStartAdapter(_StartAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.startup_probes = 0

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        if not self.started:
            return OllamaProbe("stopped", binding.api_base)
        self.startup_probes += 1
        state = "healthy" if self.startup_probes >= 2 else "stopped"
        return OllamaProbe(state, binding.api_base, version="0.12.0")


class _HealthyAdapter(_StartAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.pulled: list[str] = []

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")


class _InstallingAdapter:
    platform = "linux"

    def __init__(self, directory: Path) -> None:
        self.installed = False
        self.started = False
        self.installers = 0
        self.confirmations: list[bool] = []
        self.pulled: list[str] = []
        self.installer = DownloadedInstaller(
            source_url=OFFICIAL_INSTALL_URLS["linux"],
            sha256="a" * 64,
            script_path=directory / "official-install.sh",
            command=("/bin/sh", str(directory / "official-install.sh")),
        )

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        if not self.installed:
            return OllamaProbe("absent", binding.api_base)
        return OllamaProbe(
            "healthy" if self.started else "stopped",
            binding.api_base,
            version="0.12.0",
        )

    def download_official_installer(self) -> DownloadedInstaller:
        self.installers += 1
        return self.installer

    def run_confirmed_installer(
        self, _installer: DownloadedInstaller, *, user_confirmed: bool
    ) -> None:
        self.confirmations.append(user_confirmed)
        self.installed = True

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
        self.started = True

    def list_models(self, _binding: OllamaBinding) -> tuple[str, ...]:
        return tuple(self.pulled)

    def pull_model(self, _binding: OllamaBinding, model_id: str) -> None:
        self.pulled.append(model_id)


class _RepairingAdapter(_StartAdapter):
    def __init__(self, directory: Path) -> None:
        super().__init__()
        self.directory = directory
        self.installer = DownloadedInstaller(
            source_url=OFFICIAL_INSTALL_URLS["linux"],
            sha256="a" * 64,
            script_path=directory / "official-install.sh",
            command=("/bin/sh", str(directory / "official-install.sh")),
        )
        self.start_attempts = 0

    def start_bound_installation(self, binding: OllamaBinding) -> None:
        self.start_attempts += 1
        self.started.append(binding.launch_target)
        if self.start_attempts == 1:
            raise RuntimeError("start failed")

    def download_official_installer(self) -> DownloadedInstaller:
        self.installers += 1
        return self.installer

    def run_confirmed_installer(
        self, _installer: DownloadedInstaller, *, user_confirmed: bool
    ) -> None:
        assert user_confirmed is True

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
