"""Local data deletion mechanics behind the lifecycle Uninstall Port."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.orchestration.lifecycle import UninstallState
from app.orchestration.lifecycle.ports import LifecycleLocalDataPort
from infrastructure.persistence.layout.data_layout import final_root_layout


class LocalUninstallAdapter:
    def __init__(self, *, local_data: LifecycleLocalDataPort) -> None:
        self._local_data = local_data

    def state(self, elfie_home: Path | None = None) -> UninstallState:
        home = self._home(elfie_home)
        return UninstallState(
            data_home=home,
            home_exists=home.exists(),
            config_exists=(home / "configs" / "runtime.yaml").exists(),
            env_exists=(home / "configs" / "auth.env").exists(),
        )

    def delete_config(self, elfie_home: Path | None = None) -> bool:
        configs = self._home(elfie_home) / "configs"
        if not configs.exists():
            return False
        shutil.rmtree(configs)
        return True

    def delete_all(self, elfie_home: Path | None = None) -> None:
        home = self._home(elfie_home)
        if home.exists():
            shutil.rmtree(home)

    def _home(self, elfie_home: Path | None) -> Path:
        if elfie_home is None:
            return self._local_data.home()
        return final_root_layout(
            elfie_home.expanduser().resolve(strict=False)
        ).data_home


__all__ = ("LocalUninstallAdapter",)
