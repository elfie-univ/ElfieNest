"""Application composition root."""

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "ApplicationContainer": (".container", "ApplicationContainer"),
    "ProcessDiagnosticsHandle": (".diagnostics", "ProcessDiagnosticsHandle"),
    "build_accounts_service": (".app_wiring.accounts", "build_accounts_service"),
    "build_application_container": (".container", "build_application_container"),
    "create_app": (".api", "create_app"),
    "open_core_process_diagnostics": (
        ".diagnostics",
        "open_core_process_diagnostics",
    ),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = (
    "ApplicationContainer",
    "ProcessDiagnosticsHandle",
    "build_accounts_service",
    "build_application_container",
    "create_app",
    "open_core_process_diagnostics",
)
