"""App-internal dependency wiring.

This package assembles Feature services and their App-owned adapters.  It does
not assemble cross-root runtime components; those belong to ``system_wiring``.
"""

from .accounts import build_accounts_service
from .adoption import build_adoption_services
from .cli_configuration import build_cli_configuration
from .cli_ui import build_terminal_menu
from .communication import build_communication_services
from .food import build_food_service
from .observer import build_observer_facade
from .operations import build_operations_facade
from .setup import build_setup_services
from .storage import ensure_application_storage

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
