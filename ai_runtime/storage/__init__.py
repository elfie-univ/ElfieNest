from ai_runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from ai_runtime.storage.data_home import (
    get_config_path,
    get_configs_dir,
    get_credentials_dir,
    get_db_path,
    get_elfie_conversations_dir,
    get_elfie_developer_home,
    get_elfie_home,
    get_local_files_dir,
    get_logs_dir,
    get_model_validation_dir,
    get_oauth_credentials_dir,
    get_provider_catalog_path,
    get_provider_config_path,
    get_report_database_path,
    get_report_exports_dir,
    get_reports_dir,
    get_runtime_config_paths,
    get_runtime_dir,
    get_runtime_locks_dir,
    get_runtime_state_path,
    get_runtime_validation_dir,
    get_tool_config_path,
)
from ai_runtime.storage.oauth_credentials import (
    InvalidOAuthCredentialIdError,
    OAuthCredential,
    OAuthCredentialStore,
    OAuthCredentialStoreError,
)
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionDocument,
    ProviderConnectionStore,
    ProviderConnectionStoreError,
    ProviderModelRecord,
)
from ai_runtime.storage.report_repository import (
    ReportRepository,
    ReportRun,
    ValidationObservation,
)
from ai_runtime.storage.runtime_settings import (
    read_runtime_settings,
    write_runtime_settings,
)
from ai_runtime.storage.validation_reports import (
    InvalidReportIdentityError,
    read_latest_model_validation,
    read_latest_provider_validation,
    write_model_validation_report,
    write_provider_validation_report,
)

_SECRET_EXPORTS = frozenset(
    {
        "connection_secret_name",
        "provider_secret_name",
        "read_secrets",
        "resolve_secret",
        "set_connection_secret",
        "set_provider_secret",
    }
)


def __getattr__(name: str):
    if name in _SECRET_EXPORTS:
        from ai_runtime.storage import secrets

        return getattr(secrets, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "InvalidOAuthCredentialIdError",
    "InvalidReportIdentityError",
    "OAuthCredential",
    "OAuthCredentialStore",
    "OAuthCredentialStoreError",
    "ProviderConnection",
    "ProviderConnectionDocument",
    "ProviderConnectionStore",
    "ProviderConnectionStoreError",
    "ProviderModelRecord",
    "ReportRepository",
    "ReportRun",
    "ValidationObservation",
    "get_config_path",
    "get_configs_dir",
    "get_credentials_dir",
    "get_db_path",
    "get_elfie_home",
    "get_elfie_developer_home",
    "get_elfie_conversations_dir",
    "get_logs_dir",
    "get_model_validation_dir",
    "get_local_files_dir",
    "get_oauth_credentials_dir",
    "get_provider_catalog_path",
    "get_provider_config_path",
    "get_report_database_path",
    "get_report_exports_dir",
    "get_reports_dir",
    "get_runtime_dir",
    "get_runtime_config_paths",
    "get_runtime_locks_dir",
    "get_runtime_state_path",
    "get_runtime_validation_dir",
    "get_tool_config_path",
    "provider_secret_name",
    "connection_secret_name",
    "read_secrets",
    "read_yaml_mapping",
    "read_runtime_settings",
    "read_latest_model_validation",
    "read_latest_provider_validation",
    "resolve_secret",
    "set_provider_secret",
    "set_connection_secret",
    "write_yaml_mapping",
    "write_runtime_settings",
    "write_model_validation_report",
    "write_provider_validation_report",
]
