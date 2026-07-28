"""Single-entry three-layer interactive Runtime Lab."""

from __future__ import annotations

import copy
import getpass
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.advisor import LLMFoodPlanningAdvisor, select_planning_model
from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.models import FIXED_FOOD_KINDS
from ai_runtime.food.planner import FoodPlanner, ModelEvidence
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.lab.menu import MenuItem, TerminalMenu
from ai_runtime.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from ai_runtime.models.catalog import BUILTIN_MODEL_CATALOG
from ai_runtime.providers.model_hints import (
    ProviderModelSpec,
    configured_model_specs,
    suggested_model_names,
)
from ai_runtime.providers.profiles import BUILTIN_PROFILES
from ai_runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from ai_runtime.storage.data_home import get_config_path, get_food_catalog_path
from ai_runtime.storage.secrets import (
    provider_secret_name,
    set_provider_secret,
    set_tool_secret,
)
from ai_runtime.tools.config import TOOL_KEYS, load_tool_configs
from ai_runtime.validation.agent import ModelAgentValidationRunner
from ai_runtime.validation.foods import FoodValidationRunner
from ai_runtime.validation.models import CheckStatus, ValidationReport, ValidationSuite
from ai_runtime.validation.overview import (
    RuntimeOverviewGenerator,
    RuntimeOverviewStore,
    configured_provider_ids,
    render_provider_model_matrix,
)
from ai_runtime.validation.providers import (
    ProviderValidationRunner,
    discover_provider_models,
)
from ai_runtime.validation.tools import DirectToolValidationRunner


class RuntimeLab:
    def __init__(
        self,
        *,
        config_home: Path | str | None = None,
        input_fn: Callable[[str], str] = input,
        secret_input_fn: Callable[[str], str] = getpass.getpass,
        output_fn: Callable[[str], None] = print,
        interactive: bool | None = None,
        key_reader: Callable[[], str] | None = None,
    ) -> None:
        def safe_input(prompt: str) -> str:
            try:
                return input_fn(prompt)
            except (EOFError, KeyboardInterrupt):
                return ""

        self.input = safe_input
        self.secret_input = secret_input_fn
        self.output = output_fn
        self.config_home = str(config_home) if config_home else None
        custom_io = input_fn is not input or output_fn is not print
        self.menu = TerminalMenu(
            input_fn=input_fn,
            output_fn=output_fn,
            key_reader=key_reader,
            interactive=False if custom_io and interactive is None else interactive,
        )
        self.config = LLMRuntimeConfig.load(config_home=self.config_home)

    def run(self) -> None:
        while True:
            choice = self.menu.choose(
                "ElfieNest Runtime Local Lab",
                (
                    MenuItem("1", "Provider Config"),
                    MenuItem("2", "Tool Config"),
                    MenuItem("3", "Food Config"),
                    MenuItem("4", "Overview & Reports"),
                ),
                back_label="Exit",
            )
            if choice == "1":
                self.provider_menu()
            elif choice == "2":
                self.tool_menu()
            elif choice == "3":
                self.food_menu()
            elif choice == "4":
                self.report_menu()
            elif choice is None:
                self.menu.clear()
                if not self.menu.interactive:
                    self.output("Exited Runtime Lab.")
                return

    def report_menu(self) -> None:
        while True:
            breadcrumb = "Runtime Lab / Overview & Reports"
            choice = self.menu.choose(
                "Overview & Reports",
                (
                    MenuItem("1", "View Current Overview"),
                    MenuItem("2", "Regenerate Report"),
                    MenuItem("3", "View Historical Reports"),
                ),
                breadcrumb=breadcrumb,
                back_label="Back",
            )
            if choice is None:
                return
            if choice == "1":
                self._action(
                    "Current Runtime Overview", breadcrumb, self._show_current_overview
                )
            elif choice == "2":
                self._action(
                    "Regenerate Validation Report",
                    breadcrumb,
                    self._regenerate_overview,
                )
            elif choice == "3":
                self._overview_history_menu()

    def provider_menu(self) -> None:
        while True:
            breadcrumb = "Runtime Lab / Provider Config"
            configured = configured_provider_ids(self.config)
            items = [MenuItem("1", "Provider Overview")]
            provider_by_key: dict[str, str] = {}
            for index, provider_id in enumerate(configured, 2):
                key = str(index)
                provider_by_key[key] = provider_id
                items.append(
                    MenuItem(
                        key,
                        self._provider_label(provider_id),
                        self._provider_hint(provider_id),
                    )
                )
            add_key = str(len(items) + 1)
            items.append(MenuItem(add_key, "Add Provider"))
            choice = self.menu.choose(
                "Provider Config",
                tuple(items),
                breadcrumb=breadcrumb,
                back_label="Back",
            )
            if choice is None:
                return
            if choice == "1":
                self._action(
                    "Provider × Model Overview",
                    breadcrumb,
                    self._show_provider_model_matrix,
                )
                continue
            if choice == add_key:
                self._configure_other_provider_menu()
                continue
            provider_id = provider_by_key.get(str(choice))
            if provider_id:
                self.provider_detail_menu(provider_id)

    def provider_detail_menu(self, provider_id: str) -> None:
        while True:
            breadcrumb = f"Runtime Lab / Layer 1 / {provider_id}"
            choice = self.menu.choose(
                self._provider_label(provider_id),
                (
                    MenuItem("1", "View & Status"),
                    MenuItem("2", "Modify Configuration"),
                    MenuItem("3", "Validate Connectivity"),
                    MenuItem("4", "Delete Provider"),
                ),
                breadcrumb=breadcrumb,
                back_label="Back to Provider List",
            )
            if choice is None:
                return
            if choice == "1":
                self._action(
                    f"{provider_id} Configuration & Status",
                    breadcrumb,
                    lambda provider_id=provider_id: self._show_provider_with_evidence(
                        provider_id
                    ),
                )
            elif choice == "2":
                self._action(
                    f"Configure Provider: {provider_id}",
                    breadcrumb,
                    lambda provider_id=provider_id: (
                        self._configure_provider_interactive(provider_id)
                    ),
                )
            elif choice == "3":
                self._action(
                    f"Validate Provider: {provider_id}",
                    breadcrumb,
                    lambda provider_id=provider_id: self._validate_provider_full(
                        provider_id
                    ),
                )
            elif choice == "4":
                if self._delete_provider(provider_id):
                    return

    def tool_menu(self) -> None:
        while True:
            breadcrumb = "Runtime Lab / Tool Config"
            choice = self.menu.choose(
                "Tool Config",
                (
                    MenuItem("1", "Web Search"),
                    MenuItem("2", "Code Executor"),
                    MenuItem("3", "File Access"),
                    MenuItem("4", "Skill Evolution"),
                ),
                breadcrumb=breadcrumb,
                back_label="Back",
            )
            if choice is None:
                return
            if choice == "1":
                self._web_search_menu()
            elif choice == "2":
                self._code_executor_menu()
            elif choice == "3":
                self._file_access_menu()
            elif choice == "4":
                self._skill_evolution_menu()

    def _web_search_menu(self) -> None:
        breadcrumb = "Runtime Lab / Tool Config / Web Search"
        choice = self.menu.choose(
            "Web Search Config",
            (
                MenuItem("1", "View Config"),
                MenuItem("2", "Modify Config"),
                MenuItem("3", "Validate"),
            ),
            breadcrumb=breadcrumb,
            back_label="Back",
        )
        if choice is None:
            return
        if choice == "1":
            self._action("Web Search Config", breadcrumb, self._show_tool_configs)
        elif choice == "2":
            self._configure_tool_menu()
        elif choice == "3":
            self._action("Validate Web Search", breadcrumb, self._verify_web_search)

    def _code_executor_menu(self) -> None:
        breadcrumb = "Runtime Lab / Tool Config / Code Executor"
        choice = self.menu.choose(
            "Code Executor Config",
            (
                MenuItem("1", "View Config"),
                MenuItem("2", "Modify Config"),
                MenuItem("3", "Validate"),
            ),
            breadcrumb=breadcrumb,
            back_label="Back",
        )
        if choice is None:
            return
        if choice == "1":
            self._action("Code Executor Config", breadcrumb, self._show_tool_configs)
        elif choice == "2":
            self._configure_tool_menu()
        elif choice == "3":
            self._action(
                "Validate Code Executor", breadcrumb, self._validate_code_executor
            )

    def _file_access_menu(self) -> None:
        breadcrumb = "Runtime Lab / Tool Config / File Access"
        choice = self.menu.choose(
            "File Access Config",
            (
                MenuItem("1", "View Config"),
                MenuItem("2", "Modify Config"),
                MenuItem("3", "Validate"),
            ),
            breadcrumb=breadcrumb,
            back_label="Back",
        )
        if choice is None:
            return
        if choice == "1":
            self._action("File Access Config", breadcrumb, self._show_tool_configs)
        elif choice == "2":
            self._configure_tool_menu()
        elif choice == "3":
            self._action("Validate File Access", breadcrumb, self._validate_file_access)

    def _skill_evolution_menu(self) -> None:
        breadcrumb = "Runtime Lab / Tool Config / Skill Evolution"
        choice = self.menu.choose(
            "Skill Evolution Config",
            (
                MenuItem("1", "View Config"),
                MenuItem("2", "Modify Config"),
                MenuItem("3", "Validate"),
            ),
            breadcrumb=breadcrumb,
            back_label="Back",
        )
        if choice is None:
            return
        if choice == "1":
            self._action("Skill Evolution Config", breadcrumb, self._show_tool_configs)
        elif choice == "2":
            self._configure_tool_menu()
        elif choice == "3":
            self._action(
                "Validate Skill Evolution", breadcrumb, self._validate_skill_evolution
            )

    def food_menu(self) -> None:
        store = FoodCatalogStore()
        while True:
            breadcrumb = "Runtime Lab / Layer 3"
            choice = self.menu.choose(
                "Food Strategy",
                (
                    MenuItem("1", "View Current Food Strategy"),
                    MenuItem("2", "Auto-Update Food Strategy"),
                    MenuItem("3", "Validate Current Food Strategy"),
                    MenuItem("4", "History & Rollback"),
                ),
                breadcrumb=breadcrumb,
                back_label="Back",
            )
            if choice is None:
                return
            if choice == "1":
                self._food_strategy_menu(store)
            elif choice == "2":
                self._action(
                    "Auto-Update Food Strategy",
                    breadcrumb,
                    lambda: self._update_foods(store),
                )
            elif choice == "3":
                self._action(
                    "Validate Current Food Configuration",
                    breadcrumb,
                    lambda: self._validate_foods(store),
                )
            elif choice == "4":
                self._food_history_menu(store)

    def run_offline_validation(self) -> ValidationReport:
        tool_suite = DirectToolValidationRunner(self.config).run(include_network=False)
        food_suite = FoodValidationRunner().validate(
            FoodCatalogStore().load(),
            list(ModelEvidenceStore().load().values()),
        )
        report = ValidationReport((tool_suite, food_suite))
        path = report.save()
        self._print_suite(tool_suite)
        self._print_suite(food_suite)
        self.output(f"Report saved: {path}")
        return report

    def _action(
        self,
        title: str,
        breadcrumb: str,
        action: Callable[[], Any],
    ) -> Any:
        self.menu.action_header(title, breadcrumb)
        result: Any = None
        try:
            result = action()
            return result
        except Exception as exc:
            self.output(f"Operation failed: {exc}")
            return None
        finally:
            if result is not False:
                self.menu.pause()

    def _show_current_overview(self) -> None:
        store = RuntimeOverviewStore()
        report = store.load_current()
        if report is None:
            self.output(
                "No historical validation reports，Below is current local configuration snapshot。"
            )
            report = RuntimeOverviewGenerator(self.config).snapshot()
        self._render_overview(report)

    def _regenerate_overview(self) -> None:
        providers = configured_provider_ids(self.config)
        if not providers:
            self.output("No configured Providers, cannot generate validation report.")
            return
        self.output(
            f"Validating {len(providers)} configured Providers and all their models:"
        )
        for provider_id in providers:
            self.output(f"- {provider_id}")
        self.output("Real model calls may incur costs.")
        if self.input("Confirm regenerate report? [y/N]: ").strip().lower() != "y":
            self.output("Cancelled.")
            return
        report = RuntimeOverviewGenerator(self.config).regenerate()
        path = RuntimeOverviewStore().save(report)
        self._render_overview(report)
        self.output(f"\nReport saved: {path}")

    def _render_overview(self, report: dict[str, Any]) -> None:
        summary = report.get("summary", {})
        self.output(f"Report time: {report.get('created_at', 'Unknown')}")
        self.output(
            "Providers:"
            f"Configured {summary.get('configured_providers', 0)}，"
            f"Connected {summary.get('reachable_providers', 0)}"
        )
        self.output(
            "Model Endpoints:"
            f"Total {summary.get('model_endpoints', 0)}, "
            f"Verified {summary.get('verified_model_endpoints', 0)}, "
            f"Agent verified {summary.get('agent_verified_models', 0)}"
        )
        self.output(
            "Food:"
            f"Available {summary.get('available_foods', 0)} / "
            f"{summary.get('total_foods', 0)}"
        )
        self.output("\nProvider Status:")
        for provider in report.get("providers", ()):
            if not isinstance(provider, dict):
                continue
            status = {
                "passed": "✅",
                "failed": "❌",
                "unknown": "?",
            }.get(str(provider.get("status")), "?")
            self.output(
                f"- {status} {provider.get('id')}: {provider.get('api_base', '')}"
            )
        self.output("\nProvider × Models:")
        width = shutil.get_terminal_size(fallback=(100, 30)).columns
        for line in render_provider_model_matrix(report, width=width):
            self.output(line)
        generation_note = report.get("food_generation_note")
        if generation_note:
            self.output(f"\nFood generation source: {generation_note}")

    def _overview_history_menu(self) -> None:
        store = RuntimeOverviewStore()
        versions = store.history()
        if not versions:
            self._action(
                "Historical Reports",
                "Runtime Lab / Runtime Overview & Reports",
                lambda: self.output("No Historical Reports available."),
            )
            return
        while True:
            selected = self.menu.choose(
                "Historical Reports",
                tuple(
                    MenuItem(str(index), path.stem.removeprefix("runtime-overview-"))
                    for index, path in enumerate(versions, 1)
                ),
                breadcrumb="Runtime Lab / Runtime Overview & Reports / Historical Reports",
                back_label="Back",
            )
            if selected is None:
                return
            if not selected.isdigit() or not 1 <= int(selected) <= len(versions):
                continue
            path = versions[int(selected) - 1]
            report = store.load_path(path)
            if report is not None:
                self._action(
                    path.name,
                    "Runtime Lab / Runtime Overview & Reports / Historical Reports",
                    lambda report=report: self._render_overview(report),
                )

    def _provider_hint(self, provider_id: str) -> str:
        report = RuntimeOverviewStore().load_current() or {}
        provider = next(
            (
                item
                for item in report.get("providers", ())
                if isinstance(item, dict) and item.get("id") == provider_id
            ),
            None,
        )
        if provider is None:
            return "Configured / Not Verified"
        return {
            "passed": "Configured / Connected",
            "failed": "Configured / Connection failed",
        }.get(str(provider.get("status")), "Configured / Not Verified")

    def _provider_label(self, provider_id: str) -> str:
        provider = self.config.providers.get(provider_id, {})
        display_name = str(provider.get("display_name", "")).strip()
        return f"{display_name} ({provider_id})" if display_name else provider_id

    def _show_provider_model_matrix(self) -> None:
        report = RuntimeOverviewStore().load_current()
        if report is None:
            report = RuntimeOverviewGenerator(self.config).snapshot()
            self.output(
                "No formal report available, showing based on local model evidence.\n"
            )
        width = shutil.get_terminal_size(fallback=(100, 30)).columns
        for line in render_provider_model_matrix(report, width=width):
            self.output(line)

    def _show_provider(self, provider_id: str) -> None:
        provider = self.config.providers.get(provider_id, {})
        self.output(f"Provider: {provider_id}")
        if provider.get("display_name"):
            self.output(f"Name: {provider['display_name']}")
        self.output(f"API Base：{provider.get('api_base', '')}")
        self.output(f"API Mode: {provider.get('api_mode', '')}")
        self.output(f"Auth Method: {provider.get('auth_type', '')}")
        self.output(
            f"Key: {'Configured' if provider.get('api_key') else 'Not Configured'}"
        )
        self.output(f"Config Status: {provider.get('status', 'unknown')}")
        specs = configured_model_specs(provider)
        self.output("Model Catalog:")
        for item in specs:
            capabilities = known_capabilities(item.model_id, item.display_name)
            ability = (
                f" [Known Capabilities: {_format_capabilities(capabilities)}]"
                if capabilities
                else " [Known Capabilities: To be identified]"
            )
            self.output(f"- {item.display_name}: {item.model_id}{ability}")
        if not specs:
            self.output("- Not Configured")
        self.output(
            "Note: config status≠real-time connectivity status，please run“Validate Connectivity”。"
        )

    def _show_provider_evidence(self, provider_id: str) -> None:
        evidence = [
            item
            for item in ModelEvidenceStore().load().values()
            if item.model.startswith(f"{provider_id}/")
        ]
        if not evidence:
            self.output("This Provider has no model validation records.")
            return
        for item in evidence:
            status = "✅" if item.verified else "❌"
            latency = f"{item.latency_ms:.0f}ms" if item.latency_ms else "—"
            label = item.display_name or item.model
            ability = _format_capabilities(item.capabilities)
            self.output(
                f"- {status} {label} [{item.model}]: {latency} "
                f"· Known Capability: {ability}"
            )

    def _configure_other_provider_menu(self) -> None:
        configured = set(configured_provider_ids(self.config))
        candidates = [
            provider_id
            for provider_id in BUILTIN_PROFILES
            if provider_id not in configured and provider_id != "custom_openai"
        ]
        items: list[MenuItem] = []
        builtin_by_key: dict[str, str] = {}
        for index, provider_id in enumerate(candidates, 1):
            key = str(index)
            builtin_by_key[key] = provider_id
            items.append(MenuItem(key, provider_id, BUILTIN_PROFILES[provider_id].name))
        custom_key = str(len(items) + 1)
        items.append(MenuItem(custom_key, "Add Custom Provider", "Can add multiple"))
        selected = self.menu.choose(
            "Add or configure other Provider",
            tuple(items),
            breadcrumb="Runtime Lab / Layer 1 / Add Provider",
            back_label="Back",
        )
        if selected is None:
            return
        if selected == custom_key:
            self._action(
                "Add Custom Provider",
                "Runtime Lab / Layer 1 / Add Provider",
                self._create_custom_provider,
            )
            return
        provider_id = builtin_by_key.get(selected)
        if provider_id is None:
            return
        self._action(
            f"Configure Provider: {provider_id}",
            "Runtime Lab / Layer 1 / Add Provider",
            lambda: self._configure_provider(provider_id),
        )

    def _verify_web_search(self) -> None:
        warning = self.input("Will access network, continue? [y/N]: ").strip().lower()
        if warning == "y":
            self._print_result(
                DirectToolValidationRunner(self.config).verify_web_search()
            )
        else:
            self.output("Cancelled.")

    def _show_tool_configs(self) -> None:
        configs = load_tool_configs(self.config.runtime_policy)
        labels = {
            "web_search": "Web Search",
            "local_file": "Local File",
            "code_sandbox": "Code Sandbox",
            "skills_evolution": "Skill Evolution",
        }
        for key in TOOL_KEYS:
            item = configs[key]
            status = "Enabled" if item.get("enabled") else "Disabled"
            detail = ""
            if key == "web_search":
                detail = f" / {item.get('provider', 'duckduckgo')} / Key{'Configured' if item.get('api_key') else 'Not Configured'}"
            elif key == "local_file":
                detail = f" / {item.get('root', '')}"
            elif key == "code_sandbox":
                detail = f" / {item.get('timeout_seconds', 5)}s"
            self.output(f"- {labels[key]}: {status}{detail}")

    def _configure_tool_menu(self) -> None:
        labels = {
            "web_search": "Web Search",
            "local_file": "Local File",
            "code_sandbox": "Code Sandbox",
            "skills_evolution": "Skill Evolution",
        }
        choice = self.menu.choose(
            "Configure Basic Tools",
            tuple(
                MenuItem(str(index), labels[key])
                for index, key in enumerate(TOOL_KEYS, 1)
            ),
            breadcrumb="Runtime Lab / Layer 2 / Configure Tools",
            back_label="Back",
        )
        if choice is None:
            return
        tool_key = TOOL_KEYS[int(choice) - 1]
        self._action(
            f"Configure {labels[tool_key]}",
            "Runtime Lab / Layer 2 / Configure Tools",
            lambda: self._configure_tool(tool_key),
        )

    def _configure_tool(self, tool_key: str) -> bool:
        configs = load_tool_configs(self.config.runtime_policy)
        current = dict(configs[tool_key])
        enabled = self.menu.read_text(
            f"Enable? [y/n] [{'y' if current.get('enabled') else 'n'}]: ",
            default="y" if current.get("enabled") else "n",
        )
        if enabled is None:
            return False
        current["enabled"] = enabled.lower() == "y"
        pending_secret: str | None = None
        if tool_key == "web_search":
            provider = self.menu.read_text(
                "Search Provider [duckduckgo/brave/tavily]: ",
                default=str(current.get("provider") or "duckduckgo"),
            )
            if provider is None or provider not in {"duckduckgo", "brave", "tavily"}:
                self.output("Cancelled or Provider invalid.")
                return False
            current["provider"] = provider
            api_base = self.menu.read_text(
                "API Base (empty for Provider default): ",
                default=str(current.get("api_base") or ""),
            )
            if api_base is None:
                return False
            current["api_base"] = api_base
            api_key = self.menu.read_text(
                "API Key (empty to keep, - to clear, Esc to cancel): ",
                masked=True,
                line_input=self.secret_input,
            )
            if api_key is None:
                return False
            if api_key == "-":
                pending_secret = ""
            elif api_key:
                pending_secret = api_key
            count = self.menu.read_text(
                "Default results [1-10]: ",
                default=str(current.get("max_results") or 3),
            )
            if count is None:
                return False
            current["max_results"] = max(1, min(int(count), 10))
            current.pop("api_key", None)
        elif tool_key == "local_file":
            root = self.menu.read_text(
                "Allowed local root directory: ", default=str(current.get("root") or "")
            )
            if root is None or not root:
                return False
            current["root"] = root
        elif tool_key == "code_sandbox":
            timeout = self.menu.read_text(
                "Timeout seconds [1-60]: ",
                default=str(current.get("timeout_seconds") or 5),
            )
            if timeout is None:
                return False
            current["timeout_seconds"] = max(1.0, min(float(timeout), 60.0))
        policy = dict(self.config.runtime_policy)
        tools = dict(policy.get("tools", {}))
        tools[tool_key] = current
        policy["tools"] = tools
        self.config.runtime_policy = policy
        payload = self.config.to_safe_dict()
        payload["config_version"] = 2
        write_yaml_mapping(get_config_path(), payload)
        if pending_secret is not None:
            set_tool_secret(tool_key, pending_secret)
        self.config = LLMRuntimeConfig.load()
        self.output("Tool Configuration saved securely to local storage.")
        return True

    def _food_strategy_menu(self, store: FoodCatalogStore) -> None:
        while True:
            catalog = store.load()
            items = []
            keys = list(FIXED_FOOD_KINDS)
            for index, key in enumerate(keys, 1):
                kind = FIXED_FOOD_KINDS[key]
                recipe = catalog.recipes.get(key)
                model = (
                    recipe.primary.model
                    if recipe and recipe.primary.model
                    else "Not Configured"
                )
                status = recipe.validation_status.value if recipe else "missing"
                items.append(
                    MenuItem(
                        str(index),
                        f"{kind.display_name:<6} {model}",
                        status,
                    )
                )
            selected = self.menu.choose(
                "Current Food Strategy",
                tuple(items),
                breadcrumb="Runtime Lab / Layer 3 / Current Food Strategy",
                back_label="Back",
            )
            if selected is None:
                return
            if not selected.isdigit() or not 1 <= int(selected) <= len(keys):
                continue
            food_key = keys[int(selected) - 1]
            self._action(
                FIXED_FOOD_KINDS[food_key].display_name,
                "Runtime Lab / Layer 3 / Current Food Strategy",
                lambda food_key=food_key: self._show_food_detail(store, food_key),
            )

    def _show_food_detail(self, store: FoodCatalogStore, food_key: str) -> None:
        catalog = store.load()
        recipe = catalog.recipes.get(food_key)
        if recipe is None:
            self.output("This Food is not configured yet.")
            return
        self.output(f"Primary Model: {recipe.primary.model or 'Not Configured'}")
        self.output(f"Reasoning Profile: {recipe.primary.reasoning_profile.value}")
        self.output(f"Deep Model: {recipe.deep.model if recipe.deep else '—'}")
        self.output(
            f"Validation Model: {recipe.verifier.model if recipe.verifier else '—'}"
        )
        fallbacks = ", ".join(item.model for item in recipe.technical_fallbacks)
        self.output(f"Tech Fallback: {fallbacks or '—'}")
        self.output(f"Max Output: {recipe.primary.max_tokens}")
        self.output(f"Temperature: {recipe.primary.temperature}")
        self.output(f"Tools: {', '.join(recipe.primary.tools) or 'None'}")
        self.output(f"Status：{recipe.validation_status.value}")
        self.output(f"Source: {recipe.source}")
        if catalog.generation_note:
            self.output(f"Version Generation Method: {catalog.generation_note}")

    def _food_history_menu(self, store: FoodCatalogStore) -> None:
        versions = store.history_versions()
        if not versions:
            self._action(
                "History & Rollback",
                "Runtime Lab / Layer 3",
                lambda: self.output("No Food version history."),
            )
            return
        while True:
            selected = self.menu.choose(
                "History & Rollback",
                tuple(
                    MenuItem(str(index), path.stem.removeprefix("foods-"))
                    for index, path in enumerate(versions, 1)
                ),
                breadcrumb="Runtime Lab / Layer 3 / Version History",
                back_label="Back",
            )
            if selected is None:
                return
            if not selected.isdigit() or not 1 <= int(selected) <= len(versions):
                continue
            path = versions[int(selected) - 1]
            self._action(
                path.name,
                "Runtime Lab / Layer 3 / Version History",
                lambda path=path: self._show_food_history_version(store, path),
            )

    def _show_food_history_version(self, store: FoodCatalogStore, path: Path) -> None:
        catalog = FoodCatalog.from_dict(read_yaml_mapping(path))
        self.output(f"Version: {catalog.version}")
        self.output(f"Generated: {catalog.generated_at or 'Unknown'}")
        self.output(
            f"Generation Method: {catalog.generation_note or 'Old version, not recorded'}"
        )
        for key, kind in FIXED_FOOD_KINDS.items():
            recipe = catalog.recipes.get(key)
            self.output(
                f"- {kind.display_name}: "
                f"{recipe.primary.model if recipe and recipe.primary.model else 'Not Configured'}"
            )
        if self.input("Restore this version? [y/N]: ").strip().lower() == "y":
            restored = store.restore_version(path)
            self.output(f"Restored Food version {restored.version}.")

    def _update_foods(self, store: FoodCatalogStore) -> None:
        evidence = list(ModelEvidenceStore().load().values())
        if not evidence:
            self.output(
                "No model validation evidence yet. Please batch-validate models in Layer 1 first."
            )
            return
        planning_model = select_planning_model(self.config, evidence)
        planner = (
            FoodPlanner(LLMFoodPlanningAdvisor(self.config, planning_model))
            if planning_model
            else FoodPlanner()
        )
        if planning_model:
            self.output(
                f"Attempting to generate Food suggestions using planning model: {planning_model}"
            )
        else:
            self.output("No available planning model, will use deterministic rules.")
        current_catalog = store.load()
        proposal = planner.propose(evidence, current_catalog)
        if proposal.generation_sources == ("model", "rules"):
            self.output(
                "Generation Source: Model suggestions + Deterministic rule validation"
            )
        elif proposal.advisor_error:
            self.output(f"Planning model call failed: {proposal.advisor_error}")
            self.output(
                "Generation Source: Deterministic rules (auto fallback when model unavailable)"
            )
        else:
            self.output(
                "Generation Source: Deterministic rules (no available planning model)"
            )
        changed = [item for item in proposal.changes if item.change_type != "unchanged"]
        unchanged_count = len(proposal.changes) - len(changed)
        self.output("\nFood Update Preview")
        self.output("─" * 48)
        self.output(
            f"Planning to modify {len(changed)} foods, keeping {unchanged_count} unchanged."
        )
        for change in proposal.changes:
            if change.change_type == "unchanged":
                continue
            kind = FIXED_FOOD_KINDS[change.food_key]
            marker = "+" if change.change_type == "added" else "~"
            self.output(f"\n{marker} {kind.display_name} ({change.food_key})")
            old_recipe = current_catalog.recipes.get(change.food_key)
            new_recipe = proposal.catalog.recipes.get(change.food_key)
            for label, old_value, new_value in self._food_recipe_diff(
                old_recipe, new_recipe
            ):
                self.output(f"  {label}: {old_value} → {new_value}")
            for warning in change.warnings:
                self.output(f"  Warning: {warning}")
        if not proposal.has_changes:
            self.output("Current Food is already the latest configuration.")
            return
        self.output(
            "\nChanges won't be written or new version created until confirmed."
        )
        if self.menu.confirm("Confirm applying above Food updates?"):
            store.save(proposal.catalog)
            self.output("Food updates applied, old version preserved.")
            if proposal.generation_sources == ("model", "rules"):
                self.output(
                    "This Food Strategy co-generated by model suggestions and deterministic rules."
                )
            elif proposal.advisor_error:
                self.output(
                    "Planning model not available, Food Strategy generated by deterministic rules."
                )
            else:
                self.output("This Food Strategy generated by deterministic rules.")
        else:
            self.output("Updates not applied.")

    @staticmethod
    def _food_recipe_diff(old_recipe, new_recipe) -> list[tuple[str, str, str]]:
        def values(recipe) -> dict[str, str]:
            if recipe is None:
                return {}
            return {
                "Primary Model": recipe.primary.model or "Not Available",
                "Reasoning Profile": recipe.primary.reasoning_profile.value,
                "Max Output": str(recipe.primary.max_tokens),
                "Temperature": str(recipe.primary.temperature),
                "Tools": ", ".join(recipe.primary.tools) or "None",
                "Deep Model": recipe.deep.model if recipe.deep else "None",
                "Validation Model": recipe.verifier.model
                if recipe.verifier
                else "None",
                "Tech Fallback": (
                    ", ".join(item.model for item in recipe.technical_fallbacks)
                    or "None"
                ),
                "Validation Status": recipe.validation_status.value,
            }

        old_values = values(old_recipe)
        new_values = values(new_recipe)
        return [
            (label, old_values.get(label, "—"), new_values.get(label, "—"))
            for label in dict.fromkeys((*old_values, *new_values))
            if old_values.get(label, "—") != new_values.get(label, "—")
        ]

    def _validate_foods(self, store: FoodCatalogStore) -> None:
        catalog = store.load()
        referenced = self._food_referenced_models(catalog)
        if not referenced:
            self.output(
                "Current Food Strategy has no callable models, please Auto-Update Food Strategy first."
            )
            return
        model_count = sum(len(models) for models in referenced.values())
        self.output(
            f"Will make real calls to {model_count} models referenced by Food Strategy, then validate,"
            "Cloud models may incur costs."
        )
        if not self.menu.confirm(
            "Confirm starting Food integration validation?",
            accept_label="Start Validation",
            reject_label="Cancel",
        ):
            self.output("Cancelled, no pseudo-failure report generated.")
            return

        evidence_store = ModelEvidenceStore()
        evidence_before = evidence_store.load()
        provider_runner = ProviderValidationRunner(self.config)
        live_suites: list[ValidationSuite] = []
        refreshed: list[ModelEvidence] = []
        for provider_id, model_names in referenced.items():
            suite = provider_runner.verify_models(provider_id, model_names)
            live_suites.append(suite)
            self._print_suite(suite)
            for result in suite.results:
                if not result.model:
                    continue
                model_id = f"{provider_id}/{result.model}"
                previous = evidence_before.get(model_id)
                catalog_entry = BUILTIN_MODEL_CATALOG.get(model_id)
                display_name = previous.display_name if previous else result.model
                if catalog_entry:
                    capabilities = frozenset(catalog_entry.capabilities)
                else:
                    capabilities = known_capabilities(result.model, display_name)
                    if not capabilities and previous:
                        capabilities = previous.capabilities
                    if not capabilities:
                        capabilities = frozenset({"text"})
                refreshed.append(
                    ModelEvidence(
                        model=model_id,
                        display_name=canonical_display_name(result.model, display_name),
                        capabilities=capabilities,
                        verified=result.status is CheckStatus.PASSED,
                        cost_grade=(
                            catalog_entry.cost_tier
                            if catalog_entry
                            else previous.cost_grade
                            if previous
                            else 2
                        ),
                        latency_ms=result.duration_ms,
                        tool_test_passed=(
                            previous.tool_test_passed if previous else False
                        ),
                        local=provider_id == "ollama",
                    )
                )
        evidence_store.merge(refreshed)

        tool_recipe = catalog.recipes.get("tool")
        if tool_recipe and tool_recipe.primary.model:
            tool_model = evidence_store.load().get(tool_recipe.primary.model)
            if tool_model and tool_model.verified:
                provider_id, model_name = tool_recipe.primary.model.split("/", 1)
                agent_suite = ModelAgentValidationRunner(self.config).verify(
                    provider_id, model_name
                )
                live_suites.append(agent_suite)
                self._print_suite(agent_suite)
                evidence_store.merge(
                    [
                        ModelEvidence(
                            model=tool_model.model,
                            display_name=tool_model.display_name,
                            capabilities=tool_model.capabilities,
                            verified=True,
                            cost_grade=tool_model.cost_grade,
                            latency_ms=tool_model.latency_ms,
                            tool_test_passed=agent_suite.passed,
                            local=tool_model.local,
                        )
                    ]
                )

        suite = FoodValidationRunner().validate(
            catalog, list(evidence_store.load().values())
        )
        self._print_suite(suite)
        path = ValidationReport((*live_suites, suite)).save()
        self.output(f"Food Validation Report Saved: {path}")

    @staticmethod
    def _food_referenced_models(catalog: FoodCatalog) -> dict[str, list[str]]:
        """Collect models actually referenced by recipes, dedupe by Provider, empty placeholders excluded."""
        grouped: dict[str, list[str]] = {}
        for recipe in catalog.recipes.values():
            profiles = [recipe.primary, recipe.deep, recipe.verifier]
            profiles.extend(recipe.technical_fallbacks)
            for profile in profiles:
                if profile is None or not profile.model or "/" not in profile.model:
                    continue
                provider_id, model_name = profile.model.split("/", 1)
                if not provider_id or not model_name:
                    continue
                grouped.setdefault(provider_id, [])
                if model_name not in grouped[provider_id]:
                    grouped[provider_id].append(model_name)
        return grouped

    def _configure_provider(self, provider_id: str) -> bool:
        profile = BUILTIN_PROFILES.get(provider_id, BUILTIN_PROFILES["custom_openai"])
        original = self.config.providers.get(provider_id, {})
        provider = copy.deepcopy(original)
        is_custom = (
            provider_id not in BUILTIN_PROFILES or provider_id == "custom_openai"
        )
        if is_custom:
            display_name = self.menu.read_text(
                f"Provider Name [{provider.get('display_name', '')}]: ",
                default=str(provider.get("display_name", "")),
            )
            if display_name is None:
                self.output("Cancelled, configuration not modified.")
                return False
            if not display_name:
                self.output(
                    "Provider name cannot be empty, configuration not modified."
                )
                return False
            provider["display_name"] = display_name
        current_base = str(provider.get("api_base") or profile.api_base)
        api_base = self.menu.read_text(
            f"API Base [{current_base}]: ", default=current_base
        )
        if api_base is None:
            self.output("Cancelled, configuration not modified.")
            return False
        provider["api_base"] = api_base
        provider["api_mode"] = str(provider.get("api_mode") or profile.api_mode)
        provider["auth_type"] = str(provider.get("auth_type") or profile.auth_type)
        pending_secret: str | None = None
        if provider["auth_type"] != "none" or is_custom:
            api_key = self.menu.read_text(
                "API Key (empty to keep original, - to clear, Esc to cancel): ",
                masked=True,
                line_input=self.secret_input,
            )
            if api_key is None:
                self.output("Cancelled, configuration not modified.")
                return False
            if api_key == "-":
                pending_secret = ""
                provider["api_key"] = ""
                if is_custom:
                    provider["auth_type"] = "none"
            elif api_key:
                pending_secret = api_key
                provider["api_key"] = api_key
                if is_custom:
                    provider["auth_type"] = "bearer"
            provider["api_key_env"] = (
                provider.get("api_key_env") or profile.api_key_env_var
            )
        provider["status"] = (
            "active"
            if provider_id == "ollama" or provider.get("api_key") or is_custom
            else "inactive"
        )
        existing_specs = configured_model_specs(original)
        specs = self._refresh_specs_after_configuration(
            provider_id,
            provider,
            existing_specs=existing_specs,
            is_new=False,
        )
        if specs is None:
            self.output("Cancelled, configuration not modified.")
            return False
        self._set_provider_specs(provider, specs)
        self._commit_provider(provider_id, provider, pending_secret)
        self.output("Provider configuration saved securely to local storage.")
        if provider_id == "ollama":
            self.output(
                "Tip: Only configure Ollama address here.Models need“Batch Validation”,"
                "and will enter new routing only after Layer 3 Food generation/update."
            )
        return True

    def _create_custom_provider(self) -> bool:
        display_name = self.menu.read_text("Provider Name (Esc to cancel): ")
        if display_name is None:
            self.output("Cancelled, Provider not created.")
            return False
        if not display_name:
            self.output("Provider name cannot be empty, not created.")
            return False
        provider_id = self._next_custom_provider_id(display_name)
        template = BUILTIN_PROFILES["custom_openai"]
        api_base = self.menu.read_text(
            f"API Base [{template.api_base}]: ", default=template.api_base
        )
        if api_base is None:
            self.output("Cancelled, Provider not created.")
            return False
        api_key = self.menu.read_text(
            "API Key (optional, Esc to cancel): ",
            masked=True,
            line_input=self.secret_input,
        )
        if api_key is None:
            self.output("Cancelled, Provider not created.")
            return False

        provider: dict[str, Any] = {
            "display_name": display_name,
            "api_base": api_base,
            "api_mode": "chat_completions",
            "auth_type": "bearer" if api_key else "none",
            "api_key_env": provider_secret_name(provider_id),
            "status": "active",
        }
        if api_key:
            provider["api_key"] = api_key
        specs = self._refresh_specs_after_configuration(
            provider_id,
            provider,
            existing_specs=(),
            is_new=True,
        )
        if not specs:
            self.output("Not Configured available models, no Provider created.")
            return False
        self._set_provider_specs(provider, specs)
        self._commit_provider(provider_id, provider, api_key if api_key else None)
        self.output(f"Created Custom Provider: {display_name} ({provider_id})")
        return True

    def _refresh_specs_after_configuration(
        self,
        provider_id: str,
        provider: dict[str, Any],
        *,
        existing_specs: tuple[ProviderModelSpec, ...] | list[ProviderModelSpec],
        is_new: bool,
    ) -> list[ProviderModelSpec] | None:
        self.output("Auto-pulling model list…")
        try:
            specs = self._auto_discover_model_specs(provider_id, provider)
        except Exception as exc:
            self.output(f"Auto-pull failed: {exc}")
        else:
            if specs:
                self.output(f"Auto-updated {len(specs)} models.")
                return specs
            self.output("Auto-pull returned no models.")

        defaults = list(existing_specs) or [
            ProviderModelSpec(model_id, model_id)
            for model_id in suggested_model_names(str(provider.get("api_base", "")))
        ]
        if existing_specs and not is_new:
            edit = self.menu.read_text(
                "Will keep current model catalog, edit manually now? [y/N]: ",
                default="n",
            )
            if edit is None:
                return None
            if edit.lower() != "y":
                self.output("Auto-update failed, original model directory preserved.")
                return list(existing_specs)
        else:
            self.output("Please manually configure at least one model to continue.")
        return self._prompt_manual_model_specs(defaults)

    def _auto_discover_model_specs(
        self, provider_id: str, provider: dict[str, Any]
    ) -> list[ProviderModelSpec]:
        draft_config = copy.deepcopy(self.config)
        draft_config.providers[provider_id] = provider
        models = discover_provider_models(
            provider_id,
            draft_config,
            allow_configured_fallback=False,
        )
        return [
            ProviderModelSpec(model.name, model.display_name or model.name)
            for model in models
        ]

    def _prompt_manual_model_specs(
        self, defaults: list[ProviderModelSpec]
    ) -> list[ProviderModelSpec] | None:
        specs: list[ProviderModelSpec] = []
        index = 0
        while True:
            default = defaults[index] if index < len(defaults) else None
            model_id = self.menu.read_text(
                f"Model {index + 1} ID [{default.model_id if default else ''}]: ",
                default=default.model_id if default else "",
            )
            if model_id is None:
                return None
            if not model_id:
                self.output("Model ID cannot be empty.")
                return None
            display_default = default.display_name if default else model_id
            display_name = self.menu.read_text(
                f"Display Name [{display_default}]: ", default=display_default
            )
            if display_name is None:
                return None
            specs.append(ProviderModelSpec(model_id, display_name or model_id))
            has_more_defaults = index + 1 < len(defaults)
            more_default = "y" if has_more_defaults else "n"
            more = self.menu.read_text(
                "Continue to next model? [Y/n]: "
                if has_more_defaults
                else "Continue adding models? [y/N]: ",
                default=more_default,
            )
            if more is None:
                return None
            if more.lower() != "y":
                return specs
            index += 1

    def _set_provider_specs(
        self, provider: dict[str, Any], specs: list[ProviderModelSpec]
    ) -> None:
        provider["models"] = [
            {"id": item.model_id, "display_name": item.display_name} for item in specs
        ]
        if specs:
            provider["test_model"] = specs[0].model_id

    def _commit_provider(
        self,
        provider_id: str,
        provider: dict[str, Any],
        pending_secret: str | None,
    ) -> None:
        self.config.providers[provider_id] = provider
        payload = self.config.to_safe_dict()
        payload["config_version"] = 2
        write_yaml_mapping(get_config_path(), payload)
        if pending_secret is not None:
            set_provider_secret(provider_id, pending_secret)
        self.config = LLMRuntimeConfig.load()

    def _next_custom_provider_id(self, display_name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_")
        base = f"custom_{slug or 'provider'}"
        candidate = base
        suffix = 2
        while candidate in self.config.providers:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    def _update_provider_models(self, provider_id: str) -> bool:
        provider = copy.deepcopy(self.config.providers.get(provider_id, {}))
        existing = configured_model_specs(provider)
        self.output("Updating Model List based on current Provider configuration…")
        try:
            specs = self._auto_discover_model_specs(provider_id, provider)
            if not specs:
                raise RuntimeError("Provider returned no models")
        except Exception as exc:
            self.output(f"Auto-update failed: {exc}")
            edit = self.menu.read_text(
                "Edit Manual Model Catalog? [y/N]: ", default="n"
            )
            if edit is None or edit.lower() != "y":
                self.output("Current model catalog preserved.")
                return False
            specs = self._prompt_manual_model_specs(existing)
            if not specs:
                self.output("Model catalog not modified.")
                return False
        if not specs:
            self.output("Provider returned no models, original catalog preserved.")
            return False
        self._set_provider_specs(provider, specs)
        self._commit_provider(provider_id, provider, None)
        self.output(f"Model catalog updated, total {len(specs)} models:")
        for item in specs:
            self.output(f"- {item.display_name}: {item.model_id}")
        return True

    def _edit_manual_models(self, provider_id: str) -> bool:
        provider = copy.deepcopy(self.config.providers.get(provider_id, {}))
        specs = self._prompt_manual_model_specs(configured_model_specs(provider))
        if not specs:
            self.output("Model catalog not modified.")
            return False
        self._set_provider_specs(provider, specs)
        self._commit_provider(provider_id, provider, None)
        self.output(f"Manual model catalog saved, total {len(specs)} models.")
        return True

    def _batch_verify_models(self, provider_id: str) -> None:
        try:
            models = discover_provider_models(provider_id, self.config)
        except Exception as exc:
            self.output(f"Model discovery failed: {exc}")
            return

        if not models:
            self.output("No models to validate.")
            return

        provider = self.config.providers.get(provider_id, {})
        test_model = str(provider.get("test_model", "")).strip()

        self.output(f"\nFound {len(models)} models:")
        for idx, model in enumerate(models, 1):
            test_mark = " ✅" if model.name == test_model else ""
            self.output(
                f"  {idx}. {model.display_name or model.name} ({model.name}){test_mark}"
            )

        if all(model.source == "configured" for model in models):
            self.output(
                "\nFailed to auto-pull models, will validate manually configured model IDs."
            )

        recommended_model = test_model or (models[0].name if models else "")
        choice = self.menu.choose(
            "Select Validation Scope",
            (
                MenuItem(
                    "1", f"Validation test model: {recommended_model}", "Recommended"
                ),
                MenuItem("2", "Validate first N models"),
                MenuItem("3", "Manually select models"),
                MenuItem("4", f"Validate all {len(models)} models", "May take long"),
            ),
            breadcrumb=f"Runtime Lab / Layer 1 / {provider_id}",
            back_label="Back",
        )

        if choice is None:
            return

        selected_models = []
        if choice == "1":
            test_name = test_model or (models[0].name if models else "")
            selected_models = [m for m in models if m.name == test_name]
            if not selected_models and models:
                selected_models = [models[0]]
        elif choice == "2":
            n_str = self.input(f"Validate first N models? [1-{len(models)}]: ").strip()
            try:
                n = int(n_str)
                n = max(1, min(n, len(models)))
                selected_models = models[:n]
            except ValueError:
                self.output("Invalid input, cancelled.")
                return
        elif choice == "3":
            self.output(
                "\nEnter model numbers to validate, space-separated (e.g., 1 3 5):"
            )
            indices_str = self.input("Numbers: ").strip()
            try:
                indices = [int(x) for x in indices_str.split()]
                selected_models = [
                    models[i - 1] for i in indices if 1 <= i <= len(models)
                ]
            except (ValueError, IndexError):
                self.output("Invalid input, cancelled.")
                return
        elif choice == "4":
            selected_models = models
            self.output(f"\n⚠️  Validating all {len(models)} models, may take a while.")
            if self.input("Confirm to continue? [y/N]: ").strip().lower() != "y":
                self.output("Cancelled.")
                return

        if not selected_models:
            self.output("No models selected.")
            return

        self.output(f"\nStarting validation of {len(selected_models)} models...\n")

        results = []
        runner = ProviderValidationRunner(self.config)

        for idx, model in enumerate(selected_models, 1):
            self.output(
                f"[{idx}/{len(selected_models)}] Validating: {model.display_name or model.name} ({model.name})..."
            )

            try:
                result = runner.verify_model(provider_id, model.name)
                results.append(result)

                status_mark = "✅" if result.status == CheckStatus.PASSED else "❌"
                self.output(
                    f"  {status_mark} {result.message} ({result.duration_ms:.0f}ms)"
                )
            except KeyboardInterrupt:
                self.output("\n\nUser interrupted validation.")
                break
            except Exception as exc:
                self.output(f"  ❌ Validation failed: {exc}")
                if idx < len(selected_models):
                    cont = (
                        self.input("\nContinue validating remaining models? [Y/n]: ")
                        .strip()
                        .lower()
                    )
                    if cont == "n":
                        self.output("Cancelled remaining validations.")
                        break

        if results:
            suite = ValidationSuite(
                name=f"provider:{provider_id}",
                results=tuple(results),
            )
            self._print_suite(suite)

            evidence = []
            model_by_id = {model.name: model for model in models}
            for result in results:
                model_id = f"{provider_id}/{result.model}"
                catalog_entry = BUILTIN_MODEL_CATALOG.get(model_id)
                discovered_name = (
                    model_by_id[result.model].display_name
                    if result.model in model_by_id
                    else result.model or ""
                )
                known = known_capabilities(result.model or "", discovered_name)
                evidence.append(
                    ModelEvidence(
                        model=model_id,
                        display_name=canonical_display_name(
                            result.model or "", discovered_name
                        ),
                        capabilities=frozenset(
                            catalog_entry.capabilities
                            if catalog_entry
                            else known or ("text",)
                        ),
                        verified=result.status is CheckStatus.PASSED,
                        cost_grade=catalog_entry.cost_tier if catalog_entry else 2,
                        latency_ms=result.duration_ms,
                        local=provider_id == "ollama",
                    )
                )
            ModelEvidenceStore().merge(evidence)
            path = ValidationReport((suite,)).save()
            self.output(f"\nValidation evidence and Report Saved: {path}")
            self.output(
                "Next: Enter Layer 3 to generate/update Food, validated models will enter routing."
            )

    def _verify_model_agent(self) -> None:
        store = ModelEvidenceStore()
        available = sorted(
            (item for item in store.load().values() if item.verified),
            key=lambda item: (item.display_name or item.model, item.model),
        )
        if not available:
            self.output(
                "No validated models yet. Please batch-validate models in Layer 1 first."
            )
            return
        model_by_key: dict[str, ModelEvidence] = {}
        items = [
            MenuItem("1", "Validate all available models", f"Total {len(available)} ")
        ]
        for index, item in enumerate(available, 2):
            key = str(index)
            model_by_key[key] = item
            label = item.display_name or item.model
            items.append(MenuItem(key, label, item.model))
        choice = self.menu.choose(
            "Select Model + Agent Validation scope",
            tuple(items),
            breadcrumb="Runtime Lab / Layer 2 / Model + Agent Validation",
            back_label="Cancel",
        )
        if choice is None:
            return
        selected_models = available if choice == "1" else [model_by_key.get(choice)]
        selected_models = [item for item in selected_models if item is not None]
        if not selected_models:
            return
        self.output(
            f"Will make real calls to {len(selected_models)} models,"
            "Will validate code and local file tools separately, may incur costs."
        )
        if not self.menu.confirm(
            "Confirm starting Model + Agent Validation?",
            accept_label="Start Validation",
            reject_label="Cancel",
        ):
            self.output("Cancelled.")
            return
        runner = ModelAgentValidationRunner(self.config)
        suites: list[ValidationSuite] = []
        evidence_updates: list[ModelEvidence] = []
        for index, selected in enumerate(selected_models, 1):
            provider, model = selected.model.split("/", 1)
            self.output(
                f"\n[{index}/{len(selected_models)}] "
                f"Validating {selected.display_name or selected.model}…"
            )
            suite = runner.verify(provider, model)
            suites.append(suite)
            self._print_suite(suite)
            evidence_updates.append(
                ModelEvidence(
                    model=selected.model,
                    display_name=selected.display_name,
                    capabilities=selected.capabilities,
                    verified=selected.verified,
                    cost_grade=selected.cost_grade,
                    latency_ms=selected.latency_ms,
                    tool_test_passed=suite.passed,
                    local=selected.local,
                )
            )
        store.merge(evidence_updates)
        path = ValidationReport(tuple(suites)).save()
        passed_count = sum(suite.passed for suite in suites)
        self.output(
            f"\nModel + Agent Validation complete: Passed {passed_count} / {len(suites)}."
        )
        self.output(f"Summary evidence and report saved: {path}")

    def _print_suite(self, suite: ValidationSuite) -> None:
        self.output(f"\n[{suite.name}] {'PASSED' if suite.passed else 'FAILED'}")
        for result in suite.results:
            self._print_result(result)

    def _delete_provider(self, provider_id: str) -> bool:
        """Delete a provider configuration after safety checks and confirmation.

        Returns True if provider was deleted (caller should return to parent menu),
        False if deletion was cancelled or failed.
        """
        from ai_runtime.providers.profiles import BUILTIN_PROFILES

        if provider_id in BUILTIN_PROFILES and provider_id != "custom_openai":
            self.output(f"Cannot delete builtin provider: {provider_id}")
            self.output(
                "Builtin providers can only be deactivated by clearing their API key."
            )
            return False

        food_catalog_path = get_food_catalog_path()
        if food_catalog_path.exists():
            from ai_runtime.food.store import FoodCatalogStore

            store = FoodCatalogStore()
            catalog = store.load()
            used_by_foods = []
            for food in catalog.foods:
                if food.provider == provider_id:
                    used_by_foods.append(food.name)

            if used_by_foods:
                self.output(
                    f"⚠️  Provider '{provider_id}' is used by {len(used_by_foods)} food configuration(s):"
                )
                for name in used_by_foods[:5]:
                    self.output(f"  - {name}")
                if len(used_by_foods) > 5:
                    self.output(f"  ... and {len(used_by_foods) - 5} more")
                self.output()
                self.output(
                    "Please update or remove these food configurations before deleting the provider."
                )
                return False

        self.output(f"⚠️  You are about to delete provider: {provider_id}")
        self.output("This action cannot be undone.")
        confirm = self.menu.read_text(
            "Type 'DELETE' to confirm, or press Enter to cancel: ",
            default="",
        )

        if confirm != "DELETE":
            self.output("Deletion cancelled.")
            return False

        try:
            if provider_id in self.config.providers:
                del self.config.providers[provider_id]

            payload = self.config.to_safe_dict()
            payload["config_version"] = 2
            write_yaml_mapping(get_config_path(), payload)

            from ai_runtime.storage.secrets import set_provider_secret

            set_provider_secret(provider_id, "")

            self.config = LLMRuntimeConfig.load(config_home=self.config_home)

            self.output(f"✅ Provider '{provider_id}' has been deleted.")
            return True

        except Exception as e:
            self.output(f"❌ Failed to delete provider: {e}")
            return False

    def _print_result(self, result: Any) -> None:
        icon = {
            CheckStatus.PASSED: "✅",
            CheckStatus.FAILED: "❌",
            CheckStatus.WARNING: "!",
            CheckStatus.SKIPPED: "-",
        }.get(result.status, "-")
        latency = (
            f" ({result.duration_ms:.1f}ms)" if result.duration_ms is not None else ""
        )
        self.output(f"{icon} {result.check_id}: {result.message}{latency}")


def _format_capabilities(capabilities: frozenset[str] | set[str]) -> str:
    labels = {
        "text": "Text",
        "reasoning": "Reasoning",
        "vision": "Vision",
        "audio": "Audio",
        "code": "Code",
        "tools": "Tools",
    }
    order = ("text", "reasoning", "vision", "audio", "code", "tools")
    known = [labels[item] for item in order if item in capabilities]
    extra = sorted(item for item in capabilities if item not in labels)
    return "/".join((*known, *extra)) or "Unknown"

    def _show_provider_with_evidence(self, provider_id: str) -> None:
        """Show provider config and validation evidence together."""
        self._show_provider(provider_id)
        self.output()
        self.output("Model Validation Results:")
        self.output("─" * 60)
        self._show_provider_evidence(provider_id)

    def _validate_code_executor(self) -> None:
        self.output("Code Executor validation not implemented yet")

    def _validate_file_access(self) -> None:
        self.output("File Access validation not implemented yet")

    def _validate_skill_evolution(self) -> None:
        self.output("Skill Evolution validation not implemented yet")

    def _validate_provider_full(self, provider_id: str) -> None:
        """Validate provider connectivity and all models."""
        self.output("Validating connectivity...")
        result = ProviderValidationRunner(self.config).verify_provider(provider_id)
        self._print_result(result)
        self.output()
        self.output("Validating all models...")
        self._batch_verify_models(provider_id)

    def _configure_provider_interactive(self, provider_id: str) -> bool:
        """Interactive configuration with current values display."""
        return self._configure_provider(provider_id)

    def _show_provider_with_evidence(self, provider_id: str) -> None:
        """Show provider config and validation evidence together."""
        self._show_provider(provider_id)
        self.output()
        self.output("Model Validation Results:")
        self.output("─" * 60)
        self._show_provider_evidence(provider_id)

    def _validate_code_executor(self) -> None:
        self.output("Code Executor validation not implemented yet")

    def _validate_file_access(self) -> None:
        self.output("File Access validation not implemented yet")

    def _validate_skill_evolution(self) -> None:
        self.output("Skill Evolution validation not implemented yet")

    def _validate_provider_full(self, provider_id: str) -> None:
        """Validate provider connectivity and all models."""
        self.output("Validating connectivity...")
        result = ProviderValidationRunner(self.config).verify_provider(provider_id)
        self._print_result(result)
        self.output()
        self.output("Validating all models...")
        self._batch_verify_models(provider_id)

    def _configure_provider_interactive(self, provider_id: str) -> bool:
        """Interactive configuration with current values display."""
        return self._configure_provider(provider_id)


def main() -> None:
    RuntimeLab().run()
