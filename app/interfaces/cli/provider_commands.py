from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    ChangeProviderConnectionLifecycleCommand,
    ConnectionUpdateField,
    CreateProviderConnectionCommand,
    DeleteProviderConnectionCommand,
    ProviderModelInput,
    ProviderProductResult,
    ProvidersError,
    ProvidersService,
    RemoveLocalProviderConnectionCommand,
    UpdateProviderConnectionCommand,
    VerifyProviderConnectionCommand,
)
from app.interfaces.cli.provider_projection import (
    connection_for_catalog,
    products,
    provider_rows,
)
from app.interfaces.cli.tui.common import input_password, input_text

CUSTOM_OPENAI_PROVIDER_ID = "custom_openai"


@dataclass(frozen=True)
class ProviderLoginInput:
    display_name: str
    api_key: str
    base_url: str
    test_model: str


def login_provider(
    providers: ProvidersService,
    principal: AccountPrincipal,
    provider_id: str,
) -> None:
    product = _product(providers, principal, provider_id)
    if product is None:
        _print_unknown_provider(providers, principal, provider_id)
        return

    login_input = _prompt_login_input(provider_id, product)
    if login_input is None:
        return

    print("\n  ⏳ Verifying connectivity...")
    models = (
        (ProviderModelInput(model_id=login_input.test_model),)
        if login_input.test_model
        else ()
    )
    existing = connection_for_catalog(providers, principal, provider_id)
    try:
        if existing is None:
            saved = asyncio.run(
                providers.create_connection(
                    principal,
                    CreateProviderConnectionCommand(
                        catalog_id=provider_id,
                        alias=login_input.display_name or product.name,
                        api_base=login_input.base_url,
                        api_key=login_input.api_key or None,
                        api_mode=product.api_mode,
                        auth_type=product.auth_type,
                        models=models,
                        verify=True,
                    ),
                )
            )
        else:
            fields: set[ConnectionUpdateField] = {
                "api_base",
                "api_mode",
                "auth_type",
            }
            if login_input.test_model:
                fields.add("models")
            if product.connection_method != "local":
                fields.add("api_key")
            if login_input.display_name:
                fields.add("alias")
            saved = asyncio.run(
                providers.update_connection(
                    principal,
                    UpdateProviderConnectionCommand(
                        connection_id=existing.connection_id,
                        fields=frozenset(fields),
                        alias=login_input.display_name or None,
                        api_base=login_input.base_url,
                        api_key=login_input.api_key or None,
                        api_mode=product.api_mode,
                        auth_type=product.auth_type,
                        models=models if login_input.test_model else None,
                        verify=True,
                    ),
                )
            )
    except ProvidersError as error:
        print(f"  ❌ Configuration could not be saved: {error}")
        return

    verification = saved.verification
    if verification.status != "passed":
        verification_error = (
            verification.error or verification.reason or "unknown error"
        )
        print(f"  ⚠️  Connectivity verification failed: {verification_error}")
        print(
            "  Config will still be saved. Test again later with: elfienest providers test\n"
        )
    else:
        print(
            f"  ✅ Connectivity verified! Latency: {verification.latency_ms or 0:.0f}ms\n"
        )

    print(f"  ✅ {saved.alias} configuration saved")


def _prompt_login_input(
    provider_id: str,
    product: ProviderProductResult,
) -> ProviderLoginInput | None:
    print(f"\n🔑 Configure {product.name} provider\n")

    if provider_id == CUSTOM_OPENAI_PROVIDER_ID:
        return _prompt_custom_openai_login()
    return _prompt_builtin_provider_login(product)


def _prompt_custom_openai_login() -> ProviderLoginInput | None:
    display_name = (input_text("  Name") or "").strip()
    if not display_name:
        print("❌ Name cannot be empty")
        return None

    base_url = (input_text("  Endpoint / Base URL") or "").strip()
    if not base_url:
        print("❌ Endpoint / Base URL cannot be empty")
        return None

    test_model = (input_text("  Test model") or "").strip()
    if not test_model:
        print("❌ Test model cannot be empty")
        return None

    api_key = input_password("  API Key") or ""
    if not api_key:
        print("❌ API Key cannot be empty")
        return None

    return ProviderLoginInput(
        display_name,
        api_key,
        _normalized_base_url(base_url),
        test_model,
    )


def _prompt_builtin_provider_login(
    product: ProviderProductResult,
) -> ProviderLoginInput | None:
    api_key = ""
    if product.connection_method != "local":
        api_key = input_password("  API Key") or ""
        if not api_key:
            print("❌ API Key cannot be empty")
            return None
    else:
        print("  ℹ️  Ollama doesn't require API Key, skipping")

    base_url_hint = f"Press Enter for default {product.api_base}"
    base_url_input = (input_text(f"  Base URL ({base_url_hint})") or "").strip()
    return ProviderLoginInput(
        display_name="",
        api_key=api_key,
        base_url=_normalized_base_url(base_url_input or product.api_base),
        test_model="",
    )


def _normalized_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    suffix = "/chat/completions"
    return normalized[: -len(suffix)] if normalized.endswith(suffix) else normalized


def dispatch_providers(
    providers: ProvidersService,
    principal: AccountPrincipal,
    subcmd: Optional[str],
    provider_id: Optional[str],
) -> None:
    command = subcmd or "list"
    if command == "list":
        list_providers(providers, principal)
    elif command == "test" and provider_id:
        test_provider(providers, principal, provider_id)
    elif command == "add" and provider_id:
        login_provider(providers, principal, provider_id)
    elif command == "remove" and provider_id:
        remove_provider(providers, principal, provider_id)


def list_providers(
    providers: ProvidersService,
    principal: AccountPrincipal,
) -> None:
    print("\n  📋 Provider List\n")
    print(f"  {'ID':<12s} {'Name':<20s} {'Status':<8s} {'API Mode':<20s}")
    print("  " + "-" * 70)
    for row in provider_rows(providers, principal):
        status_icon = "✅" if row.status == "active" else "⭕"
        status_text = f"{status_icon} {row.status}"
        print(
            f"  {row.provider_id:<12s} {row.name:<20s} {status_text:<8s} {row.api_mode:<20s}"
        )
    print()


def test_provider(
    providers: ProvidersService,
    principal: AccountPrincipal,
    provider_id: str,
) -> None:
    product = _product(providers, principal, provider_id)
    if product is None:
        print(f"❌ Unknown provider: {provider_id}")
        return
    connection = connection_for_catalog(providers, principal, provider_id)
    name = connection.alias if connection else product.name
    print(f"\n  ⏳ Testing {name} connectivity...\n")
    if connection is None:
        print(f"  ❌ {name} unavailable: not configured\n")
        return
    try:
        result = asyncio.run(
            providers.verify_connection(
                principal,
                VerifyProviderConnectionCommand(connection.connection_id),
            )
        ).verification
    except ProvidersError as error:
        print(f"  ❌ {name} unavailable: {error}\n")
        return
    if result.status == "passed":
        print(f"  ✅ {name} available, latency: {result.latency_ms or 0:.0f}ms")
    else:
        print(f"  ❌ {name} unavailable: {result.error or 'unknown error'}")
    print()


def remove_provider(
    providers: ProvidersService,
    principal: AccountPrincipal,
    provider_id: str,
) -> None:
    product = _product(providers, principal, provider_id)
    if product is None:
        print(f"❌ Unknown provider: {provider_id}")
        return
    connection = connection_for_catalog(providers, principal, provider_id)
    name = connection.alias if connection else product.name
    if connection is not None:
        try:
            if provider_id == "ollama":
                providers.remove_local_connection(
                    principal,
                    RemoveLocalProviderConnectionCommand(connection.connection_id),
                )
            else:
                providers.change_lifecycle(
                    principal,
                    ChangeProviderConnectionLifecycleCommand(
                        connection.connection_id, "archive"
                    ),
                )
                providers.delete_connection(
                    principal,
                    DeleteProviderConnectionCommand(connection.connection_id),
                )
        except ProvidersError as error:
            print(f"  ❌ {name} configuration could not be removed: {error}")
            return
    print(f"\n  ✅ {name} configuration removed")


def _product(
    providers: ProvidersService,
    principal: AccountPrincipal,
    provider_id: str,
) -> ProviderProductResult | None:
    return next(
        (
            product
            for product in products(providers, principal)
            if product.catalog_id == provider_id
        ),
        None,
    )


def _print_unknown_provider(
    providers: ProvidersService,
    principal: AccountPrincipal,
    provider_id: str,
) -> None:
    print(f"❌ Unknown provider: {provider_id}")
    print("\nAvailable providers:")
    for product in products(providers, principal):
        print(f"  • {product.catalog_id:12s} - {product.name}")
