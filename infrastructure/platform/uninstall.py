"""Local data deletion mechanics behind the lifecycle Uninstall Port."""

from __future__ import annotations

import shutil

from app.orchestration.lifecycle import UninstallState
from infrastructure.persistence.layout.data_home import get_elfie_home


class LocalUninstallAdapter:
    def state(self) -> UninstallState:
        home = get_elfie_home()
        return UninstallState(
            data_home=home,
            home_exists=home.exists(),
            config_exists=(home / "configs" / "runtime.yaml").exists(),
            env_exists=(home / "configs" / "auth.env").exists(),
        )

    def delete_config(self) -> bool:
        configs = get_elfie_home() / "configs"
        if not configs.exists():
            return False
        shutil.rmtree(configs)
        return True

    def delete_all(self) -> None:
        home = get_elfie_home()
        if home.exists():
            shutil.rmtree(home)


__all__ = ("LocalUninstallAdapter",)
