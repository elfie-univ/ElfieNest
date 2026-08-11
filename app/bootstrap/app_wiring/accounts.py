"""Accounts composition shared by HTTP and local CLI entry points."""

from __future__ import annotations

from app.features.accounts import AccountsService
from infrastructure.persistence.accounts import SQLiteAccountsAdapter
from infrastructure.persistence.layout.data_home import (
    data_home_from_db_path,
    get_config_path,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.platform import (
    RuntimeSecurityPolicyAdapter,
    RuntimeSettingsAdapter,
    SettingsAccountQuotaPolicyAdapter,
)


def build_accounts_service(
    db_path: str,
    *,
    settings: RuntimeSettingsAdapter | None = None,
) -> AccountsService:
    """Build one Accounts facade without exposing concrete adapters to callers."""
    config_path = get_config_path()
    if db_path != ":memory:":
        config_path = final_root_layout(data_home_from_db_path(db_path)).runtime_config
    settings_adapter = settings or RuntimeSettingsAdapter(config_path)
    accounts_adapter = SQLiteAccountsAdapter(db_path)
    return AccountsService(
        sessions=accounts_adapter,
        security_policy=RuntimeSecurityPolicyAdapter(settings_adapter),
        management=accounts_adapter,
        avatars=accounts_adapter,
        quota_policy=SettingsAccountQuotaPolicyAdapter(settings_adapter),
        initial_owner_seed=accounts_adapter,
    )


__all__ = ("build_accounts_service",)
