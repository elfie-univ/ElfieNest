from __future__ import annotations

from dataclasses import replace

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    ProviderBrandResult,
    ProviderConnectionDeletedResult,
    ProviderConnectionResult,
    ProviderConnectionVerificationResult,
    ProviderModelResult,
    ProviderProductResult,
    ProviderVerificationResult,
    SettingsService,
    StoredElfieSettings,
    StoredLoginRateLimit,
    StoredRuntimeSettings,
    StoredSecuritySettings,
)


def manager_principal() -> AccountPrincipal:
    return AccountPrincipal(1, "owner", "owner", "manage")


def verification(
    status: str = "passed",
    *,
    error: str | None = None,
) -> ProviderVerificationResult:
    return ProviderVerificationResult(
        status=status,
        checked_at="2026-08-11T00:00:00Z",
        latency_ms=12.0 if status == "passed" else None,
        error=error,
        validation_mode="full",
        cache_hit=False,
        needs_full_validation=False,
        needs_heartbeat=False,
        full_run_id=None,
        full_checked_at=None,
        heartbeat_checked_at=None,
        heartbeat_status=None,
        representative_model_id=None,
        reason=None,
    )


def product(
    catalog_id: str,
    name: str,
    *,
    local: bool = False,
) -> ProviderProductResult:
    return ProviderProductResult(
        catalog_id=catalog_id,
        name=name,
        brand=ProviderBrandResult(catalog_id, name, ""),
        connection_method="local" if local else "api_key",
        oauth_available=False,
        usage_scope="local" if local else "general",
        discovery_strategy="ollama" if local else "standard_models",
        api_mode="ollama" if local else "chat_completions",
        api_base=(
            "http://localhost:11434" if local else f"https://{catalog_id}.example/v1"
        ),
        auth_type="none" if local else "bearer",
    )


class FakeProvidersService:
    def __init__(self) -> None:
        self.products = [
            product("openai", "OpenAI"),
            product("ollama", "Ollama", local=True),
            product("custom_openai", "Custom OpenAI-compatible endpoint"),
        ]
        self.connections: list[ProviderConnectionResult] = []
        self.next_verification = verification()

    def list_products(self, principal, query):
        return tuple(self.products)

    def list_connections(self, principal, query):
        return tuple(self.connections)

    async def create_connection(self, principal, command):
        item = self._connection(
            connection_id=f"connection-{len(self.connections) + 1}",
            catalog_id=command.catalog_id,
            alias=command.alias or command.catalog_id,
            api_base=command.api_base or "",
            api_mode=command.api_mode or "chat_completions",
            auth_type=command.auth_type or "bearer",
            has_api_key=bool(command.api_key),
            models=tuple(
                self._model(model.model_id, model.display_name or model.model_id)
                for model in command.models
            ),
        )
        self.connections.append(item)
        return item

    async def update_connection(self, principal, command):
        current = next(
            item
            for item in self.connections
            if item.connection_id == command.connection_id
        )
        models = current.models
        if command.models is not None:
            models = tuple(
                self._model(model.model_id, model.display_name or model.model_id)
                for model in command.models
            )
        updated = replace(
            current,
            alias=command.alias or current.alias,
            api_base=command.api_base or current.api_base,
            api_mode=command.api_mode or current.api_mode,
            auth_type=command.auth_type or current.auth_type,
            has_api_key=(
                bool(command.api_key)
                if "api_key" in command.fields
                else current.has_api_key
            ),
            models=models,
            verification=self.next_verification,
        )
        self._replace(updated)
        return updated

    async def verify_connection(self, principal, command):
        return ProviderConnectionVerificationResult(
            command.connection_id,
            self.next_verification,
        )

    def change_lifecycle(self, principal, command):
        current = self._by_id(command.connection_id)
        updated = replace(current, enabled=False, archived=command.action == "archive")
        self._replace(updated)
        return updated

    def delete_connection(self, principal, command):
        self.connections = [
            item
            for item in self.connections
            if item.connection_id != command.connection_id
        ]
        return ProviderConnectionDeletedResult(command.connection_id)

    def remove_local_connection(self, principal, command):
        return self.delete_connection(principal, command)

    def inspect_local_provider(self, principal, query):
        return type("Local", (), {"state": "healthy"})()

    def get_model_matrix(self, principal, query):
        return type("Matrix", (), {"models": ()})()

    def add_connection(
        self,
        catalog_id: str,
        *,
        alias: str | None = None,
    ) -> ProviderConnectionResult:
        product_item = next(
            item for item in self.products if item.catalog_id == catalog_id
        )
        item = self._connection(
            connection_id=f"connection-{len(self.connections) + 1}",
            catalog_id=catalog_id,
            alias=alias or product_item.name,
            api_base=product_item.api_base,
            api_mode=product_item.api_mode,
            auth_type=product_item.auth_type,
            has_api_key=not product_item.connection_method == "local",
            models=(),
        )
        self.connections.append(item)
        return item

    def _connection(self, **values) -> ProviderConnectionResult:
        return ProviderConnectionResult(
            **values,
            enabled=True,
            archived=False,
            usage_scope="general",
            verification=self.next_verification,
        )

    def _model(self, model_id: str, display_name: str) -> ProviderModelResult:
        return ProviderModelResult(
            model_id=model_id,
            display_name=display_name,
            canonical_model_id=None,
            source="manual",
            context_window_tokens=None,
            max_output_tokens=None,
            supports_tools=None,
            supports_vision=None,
            supports_reasoning=None,
            hidden=False,
            retired=False,
            available=True,
            verification=self.next_verification,
        )

    def _by_id(self, connection_id: str) -> ProviderConnectionResult:
        return next(
            item for item in self.connections if item.connection_id == connection_id
        )

    def _replace(self, updated: ProviderConnectionResult) -> None:
        self.connections = [
            updated if item.connection_id == updated.connection_id else item
            for item in self.connections
        ]


class MemorySettingsStore:
    def __init__(self) -> None:
        self.reset_settings()

    def reset_settings(self) -> None:
        self.elfies = StoredElfieSettings(
            3,
            ("dog", "fox"),
            (("Energetic", True), ("Calm", True)),
        )
        self.runtime = StoredRuntimeSettings(1.5)
        self.security = StoredSecuritySettings(7, StoredLoginRateLimit(5, 300))

    def load_elfie_settings(self):
        return self.elfies

    def save_elfie_settings(self, settings):
        self.elfies = settings

    def load_runtime_settings(self):
        return self.runtime

    def save_runtime_settings(self, settings):
        self.runtime = settings

    def load_security_settings(self):
        return self.security

    def save_security_settings(self, settings):
        self.security = settings


def settings_service() -> SettingsService:
    return SettingsService(MemorySettingsStore())
