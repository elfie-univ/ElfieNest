"""CLI adapter for the public global capability configuration use-cases."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal
from app.features.configuration import capabilities as capabilities_feature
from app.interfaces.cli.tui.menu import MenuItem, TerminalMenuPort


def config_capabilities(
    service: capabilities_feature.CapabilitiesService,
    principal: AccountPrincipal,
    menu: TerminalMenuPort,
) -> None:
    """Configure and verify global capabilities through the Feature facade."""
    while True:
        try:
            current = service.list_capabilities(
                principal,
                capabilities_feature.ListCapabilitiesQuery(),
            )
        except capabilities_feature.CapabilitiesError as error:
            print(f"  ❌ Capability configuration unavailable: {error}")
            menu.pause()
            return

        choice = menu.choose(
            "Tool Capabilities",
            (
                MenuItem(
                    "1",
                    f"Web Search ({'enabled' if current.web_search.enabled else 'disabled'})",
                ),
                MenuItem(
                    "2",
                    f"Local File ({'enabled' if current.local_file.enabled else 'disabled'})",
                ),
                MenuItem("3", "Verify Web Search"),
                MenuItem("4", "Verify Local File"),
            ),
            breadcrumb="ElfieNest / Config / Tools",
            back_label="Back to Config",
        )
        if choice is None:
            return
        if choice == "1":
            _edit_web_search(service, principal, current.web_search, menu)
        elif choice == "2":
            _edit_local_file(service, principal, current.local_file, menu)
        elif choice == "3":
            _verify(service, principal, "web_search", menu)
        elif choice == "4":
            _verify(service, principal, "local_file", menu)


def _edit_web_search(
    service: capabilities_feature.CapabilitiesService,
    principal: AccountPrincipal,
    current: capabilities_feature.WebSearchCapabilityResult,
    menu: TerminalMenuPort,
) -> None:
    enabled = _read_bool(menu, "  Enabled", current.enabled)
    provider = menu.read_text("  Provider", default=current.provider)
    api_base = menu.read_text("  API base", default=current.api_base)
    api_key = menu.read_text("  API key (leave empty to keep)", masked=True)
    max_results = _read_int(menu, "  Max results", current.max_results)
    max_result_bytes = _read_int(
        menu,
        "  Max result bytes",
        current.max_result_bytes,
    )
    if (
        enabled is None
        or provider is None
        or api_base is None
        or max_results is None
        or max_result_bytes is None
    ):
        return
    if provider not in {"duckduckgo", "brave", "tavily"}:
        print("  ❌ Provider must be duckduckgo, brave or tavily")
        menu.pause()
        return
    if max_results < 1 or max_result_bytes < 1:
        print("  ❌ Numeric limits must be positive")
        menu.pause()
        return
    if not menu.confirm("Apply Web Search configuration?"):
        return
    try:
        service.update_web_search(
            principal,
            capabilities_feature.UpdateWebSearchCapabilityCommand(
                fields=frozenset(
                    {
                        "enabled",
                        "provider",
                        "api_base",
                        "max_results",
                        "max_result_bytes",
                    }
                ),
                enabled=enabled,
                provider=provider,
                api_base=api_base,
                api_key=api_key or None,
                max_results=max_results,
                max_result_bytes=max_result_bytes,
            ),
        )
    except capabilities_feature.CapabilitiesError as error:
        print(f"  ❌ Configuration could not be saved: {error}")
    else:
        print("  ✅ Web Search configuration saved")
    menu.pause()


def _edit_local_file(
    service: capabilities_feature.CapabilitiesService,
    principal: AccountPrincipal,
    current: capabilities_feature.LocalFileCapabilityResult,
    menu: TerminalMenuPort,
) -> None:
    enabled = _read_bool(menu, "  Enabled", current.enabled)
    max_read_bytes = _read_int(menu, "  Max read bytes", current.max_read_bytes)
    if enabled is None or max_read_bytes is None:
        return
    if max_read_bytes < 1:
        print("  ❌ Max read bytes must be positive")
        menu.pause()
        return
    if not menu.confirm("Apply Local File configuration?"):
        return
    try:
        service.update_local_file(
            principal,
            capabilities_feature.UpdateLocalFileCapabilityCommand(
                fields=frozenset({"enabled", "max_read_bytes"}),
                enabled=enabled,
                max_read_bytes=max_read_bytes,
            ),
        )
    except capabilities_feature.CapabilitiesError as error:
        print(f"  ❌ Configuration could not be saved: {error}")
    else:
        print("  ✅ Local File configuration saved")
    menu.pause()


def _verify(
    service: capabilities_feature.CapabilitiesService,
    principal: AccountPrincipal,
    capability_key: capabilities_feature.CapabilityKey,
    menu: TerminalMenuPort,
) -> None:
    try:
        result = service.verify_capability(
            principal,
            capabilities_feature.VerifyCapabilityCommand(
                capability_key=capability_key,
            ),
        )
    except capabilities_feature.CapabilitiesError as error:
        print(f"  ❌ Capability verification unavailable: {error}")
    else:
        status = "passed" if result.passed else "failed"
        print(f"  Capability: {result.name}")
        print(f"  Result: {status}")
        for item in result.results:
            print(f"    {item.check_id}: {item.status} — {item.message}")
    menu.pause()


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


def _read_int(menu: TerminalMenuPort, prompt: str, current: int) -> int | None:
    value = menu.read_text(prompt, default=str(current))
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        print("  ❌ Enter a whole number")
        return None


__all__ = ("config_capabilities",)
