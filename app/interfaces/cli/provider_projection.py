"""Provider presentation helpers shared by the CLI command and TUI surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    ListProviderConnectionsQuery,
    ListProviderProductsQuery,
    ProviderConnectionResult,
    ProviderProductResult,
    ProvidersService,
)


@dataclass(frozen=True)
class ProviderRow:
    provider_id: str
    name: str
    status: str
    api_mode: str


def products(
    providers: ProvidersService,
    principal: AccountPrincipal,
) -> tuple[ProviderProductResult, ...]:
    return providers.list_products(principal, ListProviderProductsQuery())


def connections(
    providers: ProvidersService,
    principal: AccountPrincipal,
) -> tuple[ProviderConnectionResult, ...]:
    return providers.list_connections(principal, ListProviderConnectionsQuery())


def connection_for_catalog(
    providers: ProvidersService,
    principal: AccountPrincipal,
    catalog_id: str,
) -> ProviderConnectionResult | None:
    matches = tuple(
        item
        for item in connections(providers, principal)
        if item.catalog_id == catalog_id and not item.archived
    )
    return matches[0] if matches else None


def provider_rows(
    providers: ProvidersService,
    principal: AccountPrincipal,
) -> tuple[ProviderRow, ...]:
    configured = {
        item.catalog_id: item
        for item in connections(providers, principal)
        if not item.archived
    }
    rows = tuple(
        ProviderRow(
            provider_id=product.catalog_id,
            name=(
                configured[product.catalog_id].alias
                if product.catalog_id in configured
                else product.name
            ),
            status=(
                "active"
                if product.catalog_id in configured
                and configured[product.catalog_id].enabled
                else "inactive"
            ),
            api_mode=product.api_mode,
        )
        for product in products(providers, principal)
    )
    regular = tuple(row for row in rows if row.provider_id != "custom_openai")
    custom = tuple(row for row in rows if row.provider_id == "custom_openai")
    return regular + custom


def configured_provider_rows(
    providers: ProvidersService,
    principal: AccountPrincipal,
) -> tuple[ProviderRow, ...]:
    return tuple(
        row for row in provider_rows(providers, principal) if row.status == "active"
    )


__all__ = (
    "ProviderRow",
    "configured_provider_rows",
    "connection_for_catalog",
    "connections",
    "products",
    "provider_rows",
)
