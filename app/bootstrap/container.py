"""Typed application container assembled at the production composition root."""

from __future__ import annotations

from dataclasses import dataclass

from ai_runtime.storage.data_home import data_home_from_db_path, get_config_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts import AccountsService
from infrastructure.persistence import SQLiteAccountsAdapter
from infrastructure.platform import RuntimeSecurityPolicyAdapter


@dataclass(frozen=True)
class ApplicationContainer:
    accounts: AccountsService


def build_application_container(db_path: str) -> ApplicationContainer:
    config_path = get_config_path()
    if db_path != ":memory:":
        config_path = final_root_layout(data_home_from_db_path(db_path)).runtime_config
    accounts_adapter = SQLiteAccountsAdapter(db_path)
    return ApplicationContainer(
        accounts=AccountsService(
            sessions=accounts_adapter,
            security_policy=RuntimeSecurityPolicyAdapter(config_path),
        )
    )


__all__ = ("ApplicationContainer", "build_application_container")
