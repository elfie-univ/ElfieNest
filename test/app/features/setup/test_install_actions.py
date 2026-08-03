"""Real Setup phase actions: Ollama branches, model reuse/pull, food and beds."""

from __future__ import annotations

from pathlib import Path

from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID
from ai_runtime.food.store import FoodCatalogStore
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.report_repository import ReportRepository
from app.features.setup.draft_repository import SetupDraftRepository
from app.features.setup.install_actions import run_setup_installation
from app.features.setup.service import create_first_owner_from_hash
from app.infrastructure.ollama_platform import (
    OFFICIAL_INSTALL_URLS,
    DownloadedInstaller,
    OllamaBinding,
    OllamaProbe,
)
from app.infrastructure.persistence.final_schema import create_final_nest_database
from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import get_db


def _locked_draft(db_path: str, *, use_local: bool, model_id: str | None) -> None:
    drafts = SetupDraftRepository(db_path)
    drafts.save_owner(
        account_id="owner",
        display_name="Owner",
        password_hash="pbkdf2_sha256$260000$salt$hash",
    )
    drafts.save_offline(use_local_ollama=use_local, model_id=model_id)
    drafts.save_nest(bed_count=8)
    draft = drafts.get()
    create_first_owner_from_hash(db_path, draft)
    drafts.lock()
    SetupInstallRepository(db_path).begin_or_resume()


def test_installation_without_local_ollama_skips_three_phases_and_applies_beds(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    _locked_draft(db_path, use_local=False, model_id=None)

    run_setup_installation(db_path, adapter=_UnusedAdapter())

    record = SetupInstallRepository(db_path).get()
    assert record.task_state == "completed"
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
    adapter = _StartAdapter()
    run_setup_installation(db_path, adapter=adapter)

    assert adapter.started == ["/usr/local/bin/ollama"]
    assert adapter.installers == 0
    assert SetupInstallRepository(db_path).get().task_state == "completed"


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
    food_store = FoodCatalogStore(tmp_path / "foods.yaml", tmp_path / "food-history")
    before_common = food_store.load().packages[FOOD_COMMON_ID]
    adapter = _RepairingAdapter(tmp_path)
    run_setup_installation(
        db_path,
        adapter=adapter,
        food_catalog_store=food_store,
        report_repository=ReportRepository(tmp_path / "reports.db"),
    )

    assert adapter.installers == 1
    catalog = food_store.load()
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
