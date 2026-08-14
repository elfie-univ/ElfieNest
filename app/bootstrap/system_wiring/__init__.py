"""Cross-root system wiring.

The functions exported here connect App public boundaries to Elfie, Nest and
Infrastructure runtime components.  This package is a peer of ``app_wiring``;
neither package imports the other.
"""

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "DataHomeSelectionError": (".entrypoints", "DataHomeSelectionError"),
    "build_model_execution_agent_ports": (
        ".model_execution",
        "build_model_execution_agent_ports",
    ),
    "build_nest_session_services": (".nest_session", "build_nest_session_services"),
    "create_lifecycle_facade": (".lifecycle", "create_lifecycle_facade"),
    "ensure_elfie_home": (".entrypoints", "ensure_elfie_home"),
    "get_db_path": (".entrypoints", "get_db_path"),
    "get_elfie_home": (".entrypoints", "get_elfie_home"),
    "inspect_godot_web_bundle": (".entrypoints", "inspect_godot_web_bundle"),
    "register_transient_elfie": (".nest_session", "register_transient_elfie"),
    "resolve_elfie_home": (".entrypoints", "resolve_elfie_home"),
    "restore_registered_elfies": (".nest_session", "restore_registered_elfies"),
    "select_elfie_home": (".entrypoints", "select_elfie_home"),
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
    "build_nest_session_services",
    "build_model_execution_agent_ports",
    "create_lifecycle_facade",
    "DataHomeSelectionError",
    "get_db_path",
    "get_elfie_home",
    "ensure_elfie_home",
    "inspect_godot_web_bundle",
    "register_transient_elfie",
    "restore_registered_elfies",
    "resolve_elfie_home",
    "select_elfie_home",
)
