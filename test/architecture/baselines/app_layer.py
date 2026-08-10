"""Exact temporary baseline for known App architecture violations.

The baseline is intentionally executable and reviewed.  It must equal the
current scanner output: remove entries when debt is removed, never add an entry
to make a newly introduced violation pass.
"""

from __future__ import annotations

from typing import Dict, FrozenSet

LEGACY_APP_LAYER_VIOLATIONS: Dict[str, FrozenSet[str]] = {
    "cross_feature_internal_imports": frozenset({}),
    "feature_forbidden_layer_imports": frozenset(),
    "feature_framework_imports": frozenset({}),
    "feature_public_db_path": frozenset(),
    "feature_unowned_task_calls": frozenset(),
    "infrastructure_feature_internal_imports": frozenset({}),
    "infrastructure_forbidden_layer_imports": frozenset(),
    "interface_adapter_construction": frozenset(
        {
            "app/interfaces/cli/route_commands.py::show_route::ElfieRepository",
        }
    ),
    "interface_feature_internal_imports": frozenset(
        {
            "app/interfaces/cli/model_commands.py -> app.features.configuration.provider_service",
            "app/interfaces/cli/model_commands.py -> app.features.configuration.user_config",
            "app/interfaces/cli/provider_commands.py -> app.features.configuration.provider_service",
            "app/interfaces/cli/provider_commands.py -> app.features.configuration.user_config",
            "app/interfaces/cli/tui/config_app.py -> app.features.configuration.user_config",
            "app/interfaces/cli/tui/config_editors.py -> app.features.configuration.user_config",
            "app/interfaces/cli/tui/config_views.py -> app.features.configuration.provider_service",
            "app/interfaces/cli/tui/config_views.py -> app.features.configuration.user_config",
            "app/interfaces/cli/tui/provider_menu.py -> app.features.configuration.provider_service",
            "app/interfaces/cli/tui/provider_menu.py -> app.features.configuration.user_config",
        }
    ),
    "interface_forbidden_layer_imports": frozenset(
        {
            "app/interfaces/cli/route_commands.py -> app.infrastructure.persistence.elfie_repository",
        }
    ),
    "interface_orchestration_internal_imports": frozenset(),
    "json_routes_loose_annotations": frozenset(),
    "json_routes_missing_response_model": frozenset(),
    "orchestration_forbidden_layer_imports": frozenset(),
    "unversioned_product_routes": frozenset(),
}
