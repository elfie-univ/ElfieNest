"""Exact temporary baseline for known App architecture violations.

The baseline is intentionally executable and reviewed.  It must equal the
current scanner output: remove entries when debt is removed, never add an entry
to make a newly introduced violation pass.
"""

from __future__ import annotations

from typing import Dict, FrozenSet

LEGACY_APP_LAYER_VIOLATIONS: Dict[str, FrozenSet[str]] = {
    "cross_feature_internal_imports": frozenset(
        {
        }
    ),
    "feature_forbidden_layer_imports": frozenset(),
    "feature_framework_imports": frozenset({}),
    "feature_public_db_path": frozenset(),
    "feature_unowned_task_calls": frozenset(),
    "infrastructure_feature_internal_imports": frozenset({}),
    "infrastructure_forbidden_layer_imports": frozenset(),
    "interface_adapter_construction": frozenset(
        {
            "app/interfaces/api/ollama_owner_routes.py::_provider_store::ProviderConnectionStore",
            "app/interfaces/api/owner_elfie_routes.py::_load_registered_elfies::InterfaceQueryRepository",
            "app/interfaces/api/v1/client_routes.py::_owned_public_profiles::RuntimeQueryRepository",
            "app/interfaces/cli/route_commands.py::show_route::ElfieRepository",
        }
    ),
    "interface_feature_internal_imports": frozenset(
        {
            "app/interfaces/api/ollama_owner_routes.py -> app.features.setup.ollama_owner",
            "app/interfaces/api/ollama_owner_routes.py -> app.features.setup.ollama_owner_jobs",
            "app/interfaces/api/owner_elfie_routes.py -> app.features.elfie_profile.public_projection",
            "app/interfaces/api/v1/client_routes.py -> app.features.elfie_profile.public_projection",
            "app/interfaces/cli/lifecycle_commands.py -> app.features.administration.system_service",
            "app/interfaces/cli/mobile_commands.py -> app.features.administration.system_service",
            "app/interfaces/cli/model_commands.py -> app.features.configuration.provider_service",
            "app/interfaces/cli/model_commands.py -> app.features.configuration.user_config",
            "app/interfaces/cli/provider_commands.py -> app.features.configuration.provider_service",
            "app/interfaces/cli/provider_commands.py -> app.features.configuration.user_config",
            "app/interfaces/cli/runtime_commands.py -> app.features.administration.system_service",
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
            "app/interfaces/api/app.py -> app.infrastructure.persistence.store",
            "app/interfaces/api/owner_elfie_routes.py -> app.infrastructure.persistence.interface_query_repository",
            "app/interfaces/api/v1/client_routes.py -> app.infrastructure.persistence.runtime_query_repository",
            "app/interfaces/cli/route_commands.py -> app.infrastructure.persistence.elfie_repository",
        }
    ),
    "interface_orchestration_internal_imports": frozenset(),
    "json_routes_loose_annotations": frozenset(
        {
            "app/interfaces/api/app.py::godot_web_status::GET /api/godot-web/status::return:missing",
            "app/interfaces/api/app.py::health::GET /api/health::return:missing",
            "app/interfaces/api/app.py::ws_config::GET /api/ws-config::return:loose",
            "app/interfaces/api/owner_elfie_routes.py::list_owner_elfie_monitoring::GET /elfies::return:loose",
            "app/interfaces/api/page_routes.py::owner_mobile_access::GET /api/owner/mobile-access::parameter:manager",
            "app/interfaces/api/page_routes.py::owner_mobile_access::GET /api/owner/mobile-access::return:loose",
            "app/interfaces/api/v1/client_routes.py::list_public_elfies::GET /elfies::return:loose",
            "app/interfaces/api/v1/client_routes.py::public_elfie_profile::GET /elfies/{elfie_id}/profile::return:loose",
        }
    ),
    "json_routes_missing_response_model": frozenset(
        {
            "app/interfaces/api/app.py::godot_web_status::GET /api/godot-web/status",
            "app/interfaces/api/app.py::health::GET /api/health",
            "app/interfaces/api/app.py::ws_config::GET /api/ws-config",
            "app/interfaces/api/owner_elfie_routes.py::list_owner_elfie_monitoring::GET /elfies",
            "app/interfaces/api/page_routes.py::owner_mobile_access::GET /api/owner/mobile-access",
            "app/interfaces/api/v1/client_routes.py::list_public_elfies::GET /elfies",
            "app/interfaces/api/v1/client_routes.py::public_elfie_profile::GET /elfies/{elfie_id}/profile",
        }
    ),
    "orchestration_forbidden_layer_imports": frozenset(),
    "unversioned_product_routes": frozenset(
        {
            "GET /api/godot-web/status",
            "GET /api/owner/elfies",
            "GET /api/owner/mobile-access",
            "GET /api/owner/providers/ollama",
            "GET /api/ws-config",
            "POST /api/owner/providers/ollama/install",
            "POST /api/owner/providers/ollama/models/pull",
            "POST /api/owner/providers/ollama/start",
        }
    ),
}
