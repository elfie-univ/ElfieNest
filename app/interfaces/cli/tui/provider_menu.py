from __future__ import annotations

import asyncio
from typing import Callable

from ai_runtime.lab.menu import MenuItem, TerminalMenu
from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    GetProviderModelMatrixQuery,
    ProviderConnectionResult,
    ProviderProductResult,
    ProvidersError,
    ProvidersService,
    VerifyProviderConnectionCommand,
)
from app.interfaces.cli.provider_commands import remove_provider
from app.interfaces.cli.provider_projection import connections, products

ProviderLogin = Callable[[str], None]


def config_providers(
    providers: ProvidersService,
    principal: AccountPrincipal,
    provider_login: ProviderLogin,
) -> None:
    """Preserve the existing Provider Config flow over the public Facade."""
    menu = TerminalMenu(input_fn=input, output_fn=print)
    while True:
        configured = tuple(
            item
            for item in connections(providers, principal)
            if not item.archived
        )
        items = [MenuItem("1", "Provider Overview")]
        connection_by_key: dict[str, ProviderConnectionResult] = {}
        for index, connection in enumerate(configured, 2):
            key = str(index)
            connection_by_key[key] = connection
            items.append(
                MenuItem(
                    key,
                    connection.alias,
                    "active" if connection.enabled else "inactive",
                )
            )
        add_key = str(len(items) + 1)
        items.append(MenuItem(add_key, "Add Provider"))
        choice = menu.choose(
            "Provider Config",
            tuple(items),
            breadcrumb="Runtime Lab / Provider Config",
            back_label="Back",
        )
        if choice is None:
            return
        if choice == "1":
            _show_provider_model_matrix(providers, principal)
            _pause()
        elif choice == add_key:
            _prompt_provider_login(providers, principal, provider_login)
        elif choice in connection_by_key:
            _provider_detail_menu(
                providers,
                principal,
                connection_by_key[choice],
                provider_login,
            )


def _provider_detail_menu(
    providers: ProvidersService,
    principal: AccountPrincipal,
    connection: ProviderConnectionResult,
    provider_login: ProviderLogin,
) -> None:
    menu = TerminalMenu(input_fn=input, output_fn=print)
    while True:
        current = next(
            (
                item
                for item in connections(providers, principal)
                if item.connection_id == connection.connection_id
            ),
            None,
        )
        if current is None:
            return
        choice = menu.choose(
            current.alias,
            (
                MenuItem("1", "View & Status"),
                MenuItem("2", "Modify Configuration"),
                MenuItem("3", "Validate Connectivity"),
                MenuItem("4", "Delete Provider"),
            ),
            breadcrumb=f"Runtime Lab / Layer 1 / {current.catalog_id}",
            back_label="Back to Provider List",
        )
        if choice is None:
            return
        if choice == "1":
            _show_connection(current)
            _pause()
        elif choice == "2":
            provider_login(current.catalog_id)
        elif choice == "3":
            _test_connection(providers, principal, current)
            _pause()
        elif choice == "4" and _confirm_delete(current.alias):
            remove_provider(providers, principal, current.catalog_id)
            _pause()
            return


def _show_connection(connection: ProviderConnectionResult) -> None:
    print(f"\nProvider: {connection.alias}")
    print(f"Catalog ID: {connection.catalog_id}")
    print(f"Endpoint: {connection.api_base}")
    print(f"API mode: {connection.api_mode}")
    print(f"Status: {'active' if connection.enabled else 'inactive'}")
    print(f"Models: {len(connection.models)}")
    verification = connection.verification
    print(f"Validation: {verification.status}")
    if verification.error:
        print(f"Error: {verification.error}")


def _show_provider_model_matrix(
    providers: ProvidersService,
    principal: AccountPrincipal,
) -> None:
    print("\n  📦 Provider × Model Overview\n")
    try:
        matrix = providers.get_model_matrix(
            principal,
            GetProviderModelMatrixQuery(),
        )
    except ProvidersError as error:
        print(f"  ❌ Overview unavailable: {error}")
        return
    if not matrix.models:
        print("  No configured models")
        return
    for model in matrix.models:
        available = sum(cell.available for cell in model.connections)
        capabilities = ", ".join(model.capabilities) or "-"
        print(
            f"  {model.display_name:<30s} {capabilities:<24s} "
            f"{available}/{len(model.connections)} available"
        )


def _test_connection(
    providers: ProvidersService,
    principal: AccountPrincipal,
    connection: ProviderConnectionResult,
) -> None:
    print(f"\n  Testing {connection.alias} connectivity...\n")
    try:
        result = asyncio.run(
            providers.verify_connection(
                principal,
                VerifyProviderConnectionCommand(connection.connection_id),
            )
        ).verification
    except ProvidersError as error:
        print(f"    ❌ {connection.alias}: {error}")
        return
    if result.status == "passed":
        print(f"    ✅ {connection.alias}: available ({result.latency_ms or 0:.0f}ms)")
    else:
        print(f"    ❌ {connection.alias}: {result.error or 'unknown error'}")


def _prompt_provider_login(
    providers: ProvidersService,
    principal: AccountPrincipal,
    provider_login: ProviderLogin,
) -> None:
    print("\n  Available providers:")
    available = _ordered_products(providers, principal)
    for index, product in enumerate(available, 1):
        print(f"    {index}. {product.catalog_id:12s} - {product.name}")
    try:
        selected = int(input(f"\n  Choose [1-{len(available)}]: ")) - 1
    except (KeyboardInterrupt, ValueError):
        return
    if 0 <= selected < len(available):
        provider_login(available[selected].catalog_id)


def _ordered_products(
    providers: ProvidersService,
    principal: AccountPrincipal,
) -> tuple[ProviderProductResult, ...]:
    available = products(providers, principal)
    regular = tuple(
        item for item in available if item.catalog_id != "custom_openai"
    )
    custom = tuple(item for item in available if item.catalog_id == "custom_openai")
    return regular + custom


def _confirm_delete(name: str) -> bool:
    try:
        return input(f"Delete {name}? Type 'yes' to confirm: ").strip().lower() == "yes"
    except (EOFError, KeyboardInterrupt):
        return False


def _pause() -> None:
    try:
        input("\nPress Enter to continue...")
    except (EOFError, KeyboardInterrupt):
        return


__all__ = ("ProviderLogin", "config_providers")
