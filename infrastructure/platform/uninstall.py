"""Local data deletion mechanics behind the lifecycle Uninstall Port."""

from __future__ import annotations

import shutil

from app.orchestration.lifecycle import UninstallState
from app.orchestration.lifecycle.ports import LifecycleLocalDataPort


class LocalUninstallAdapter:
    def __init__(self, *, local_data: LifecycleLocalDataPort) -> None:
        self._local_data = local_data

    def state(self) -> UninstallState:
        home = self._local_data.home()
        return UninstallState(
            data_home=home,
            home_exists=home.exists(),
            config_exists=(home / "configs" / "runtime.yaml").exists(),
            env_exists=(home / "configs" / "auth.env").exists(),
        )

    def delete_config(self) -> bool:
        configs = self._local_data.home() / "configs"
        if not configs.exists():
            return False
        shutil.rmtree(configs)
        return True

    def delete_all(self) -> None:
        home = self._local_data.home()
        if home.exists():
            shutil.rmtree(home)


__all__ = ("LocalUninstallAdapter",)
