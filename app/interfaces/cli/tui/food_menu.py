"""CLI adapter for the public Food configuration use-cases."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    ListProviderConnectionsQuery,
    ProvidersError,
    ProvidersService,
)
from app.features.configuration import food as food_feature
from app.interfaces.cli.tui.menu import MenuItem, TerminalMenuPort


def config_food(
    service: food_feature.FoodService,
    providers: ProvidersService,
    principal: AccountPrincipal,
    menu: TerminalMenuPort,
) -> None:
    """Browse and generate Food packages through the Feature facade."""
    while True:
        choice = menu.choose(
            "Food Strategy",
            (
                MenuItem("1", "View Current Food Packages"),
                MenuItem("2", "Generate Food Package"),
            ),
            breadcrumb="ElfieNest / Config / Food",
            back_label="Back to Config",
        )
        if choice is None:
            return
        if choice == "1":
            _show_catalog(service, principal, menu)
        elif choice == "2":
            _generate_food(service, providers, principal, menu)


def _show_catalog(
    service: food_feature.FoodService,
    principal: AccountPrincipal,
    menu: TerminalMenuPort,
) -> None:
    try:
        catalog = service.list_packages(
            principal,
            food_feature.ListFoodPackagesQuery(),
        )
    except food_feature.FoodError as error:
        print(f"  ❌ Food catalog unavailable: {error}")
        menu.pause()
        return

    print("\n  Current Food Packages")
    print(f"  Default: {catalog.global_default_food_id}")
    print(f"  Emergency: {catalog.global_emergency_food_id}")
    if not catalog.packages:
        print("  No Food packages configured")
    for package in catalog.packages:
        state = "enabled" if package.enabled else "disabled"
        archived = ", archived" if package.archived else ""
        print(f"  - {package.display_name} [{package.food_id}] ({state}{archived})")
        print(f"    health={package.health}, locality={package.locality}")
        print(f"    roles: {_format_roles(package.roles)}")
    menu.pause()


def _generate_food(
    service: food_feature.FoodService,
    providers: ProvidersService,
    principal: AccountPrincipal,
    menu: TerminalMenuPort,
) -> None:
    try:
        connections = tuple(
            item
            for item in providers.list_connections(
                principal,
                ListProviderConnectionsQuery(),
            )
            if item.enabled and not item.archived
        )
    except ProvidersError as error:
        print(f"  ❌ Provider connections unavailable: {error}")
        menu.pause()
        return
    if not connections:
        print("  ❌ Configure at least one active Provider before generating Food")
        menu.pause()
        return

    print("\n  Generation sources")
    for item in connections:
        print(f"  - {item.connection_id}: {item.alias} ({item.catalog_id})")
    selected = menu.read_text(
        "  Connection IDs (comma separated)",
        default=",".join(item.connection_id for item in connections),
    )
    display_name = menu.read_text("  Food name", default="Generated Food")
    local_first = _read_bool(menu, "  Prefer local models", True)
    allow_remote = _read_bool(menu, "  Allow remote models", True)
    if (
        selected is None
        or display_name is None
        or local_first is None
        or allow_remote is None
    ):
        return
    connection_ids = tuple(
        value.strip() for value in selected.split(",") if value.strip()
    )
    known_ids = {item.connection_id for item in connections}
    if not connection_ids or any(item not in known_ids for item in connection_ids):
        print("  ❌ Every connection ID must refer to an active Provider")
        menu.pause()
        return

    try:
        preview = service.preview_generation(
            principal,
            food_feature.PreviewFoodGenerationCommand(
                connection_ids=connection_ids,
                local_first=local_first,
                allow_remote=allow_remote,
                visibility_mode="global",
                visible_user_ids=(),
                display_name=display_name,
            ),
        )
    except food_feature.FoodError as error:
        print(f"  ❌ Food generation preview unavailable: {error}")
        menu.pause()
        return

    candidate = preview.candidate
    print(f"\n  Preview: {candidate.display_name}")
    print(f"  Roles: {_format_roles(candidate.roles)}")
    for warning in preview.warnings:
        print(f"  ⚠️  {warning}")
    if not menu.confirm("Create this Food package?"):
        return

    try:
        saved = service.create_package(
            principal,
            food_feature.CreateFoodPackageCommand(
                display_name=candidate.display_name,
                enabled=candidate.enabled,
                roles=_roles_input(candidate.roles),
                visibility_mode=candidate.visibility_mode,
                visible_user_ids=candidate.visible_user_ids,
            ),
        )
    except food_feature.FoodError as error:
        print(f"  ❌ Food package could not be created: {error}")
    else:
        print(f"  ✅ Food package created: {saved.food.display_name}")
    menu.pause()


def _roles_input(roles: food_feature.FoodRolesResult) -> food_feature.FoodRolesInput:
    return food_feature.FoodRolesInput(
        primary=_role_model(roles.primary),
        reasoning=_role_model(roles.reasoning),
        vision=_role_model(roles.vision),
        tool=_role_model(roles.tool),
        fallback=_role_model(roles.fallback),
    )


def _role_model(role: food_feature.FoodRoleAssignmentResult | None) -> str | None:
    return None if role is None else role.model


def _format_roles(roles: food_feature.FoodRolesResult) -> str:
    values = (
        ("primary", roles.primary),
        ("reasoning", roles.reasoning),
        ("vision", roles.vision),
        ("tool", roles.tool),
        ("fallback", roles.fallback),
    )
    return ", ".join(
        f"{name}={assignment.model if assignment is not None else '-'}"
        for name, assignment in values
    )


def _read_bool(menu: TerminalMenuPort, prompt: str, current: bool) -> bool | None:
    value = menu.read_text(prompt, default="yes" if current else "no")
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"y", "yes", "true", "1", "on", "enabled"}:
        return True
    if normalized in {"n", "no", "false", "0", "off", "disabled"}:
        return False
    print("  ❌ Enter yes or no")
    return None


__all__ = ("config_food",)
