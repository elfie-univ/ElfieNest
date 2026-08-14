"""App-internal dependency wiring.

This package assembles Feature services and their App-owned adapters.  It does
not assemble cross-root runtime components; those belong to ``system_wiring``.
"""

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "build_accounts_service": (".accounts", "build_accounts_service"),
    "build_adoption_services": (".adoption", "build_adoption_services"),
    "build_cli_configuration": (".cli_configuration", "build_cli_configuration"),
    "build_communication_services": (".communication", "build_communication_services"),
    "build_food_service": (".food", "build_food_service"),
    "build_observer_facade": (".observer", "build_observer_facade"),
    "build_operations_facade": (".operations", "build_operations_facade"),
    "build_setup_services": (".setup", "build_setup_services"),
    "build_terminal_menu": (".cli_ui", "build_terminal_menu"),
    "ensure_application_storage": (".storage", "ensure_application_storage"),
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
    "build_accounts_service",
    "build_adoption_services",
    "build_cli_configuration",
    "build_communication_services",
    "build_food_service",
    "build_observer_facade",
    "build_operations_facade",
    "build_setup_services",
    "build_terminal_menu",
    "ensure_application_storage",
)
