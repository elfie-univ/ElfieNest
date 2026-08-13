"""Cross-root system wiring.

The functions exported here connect App public boundaries to Elfie, Nest and
Infrastructure runtime components.  This package is a peer of ``app_wiring``;
neither package imports the other.
"""

from .entrypoints import (
    DataHomeSelectionError,
    ensure_elfie_home,
    get_db_path,
    get_elfie_home,
    inspect_godot_web_bundle,
    resolve_elfie_home,
    select_elfie_home,
)
from .lifecycle import create_lifecycle_facade
from .model_execution import build_model_execution_agent_ports
from .nest_session import (
    build_nest_session_services,
    register_transient_elfie,
    restore_registered_elfies,
)

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
