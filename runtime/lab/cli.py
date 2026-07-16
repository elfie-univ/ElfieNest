"""单入口三层交互式 Runtime Lab。"""

from __future__ import annotations

import copy
import getpass
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from runtime.config import LLMRuntimeConfig
from runtime.food.advisor import LLMFoodPlanningAdvisor, select_planning_model
from runtime.food.evidence import ModelEvidenceStore
from runtime.food.models import FIXED_FOOD_KINDS
from runtime.food.planner import FoodPlanner, ModelEvidence
from runtime.food.store import FoodCatalog, FoodCatalogStore
from runtime.lab.menu import MenuItem, TerminalMenu
from runtime.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from runtime.models.catalog import BUILTIN_MODEL_CATALOG
from runtime.providers.model_hints import (
    ProviderModelSpec,
    configured_model_specs,
    suggested_model_names,
)
from runtime.providers.profiles import BUILTIN_PROFILES
from runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from runtime.storage.data_home import get_config_path
from runtime.storage.secrets import (
    provider_secret_name,
    set_provider_secret,
    set_tool_secret,
)
from runtime.tools.config import TOOL_KEYS, load_tool_configs
from runtime.validation.agent import ModelAgentValidationRunner
from runtime.validation.foods import FoodValidationRunner
from runtime.validation.models import CheckStatus, ValidationReport, ValidationSuite
from runtime.validation.overview import (
    RuntimeOverviewGenerator,
    RuntimeOverviewStore,
    configured_provider_ids,
    render_provider_model_matrix,
)
from runtime.validation.providers import (
    ProviderValidationRunner,
    discover_provider_models,
)
from runtime.validation.tools import DirectToolValidationRunner


class RuntimeLab:
    def __init__(
        self,
        *,
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
        custom_io = input_fn is not input or output_fn is not print
        self.menu = TerminalMenu(
            input_fn=input_fn,
            output_fn=output_fn,
            key_reader=key_reader,
            interactive=False if custom_io and interactive is None else interactive,
        )
        self.config = LLMRuntimeConfig.load()

    def run(self) -> None:
        while True:
            choice = self.menu.choose(
                "ElfieNest Runtime 本地实验室",
                (
                    MenuItem("1", "运行总览与报告"),
                    MenuItem("2", "Provider 与原始模型", "第一层"),
                    MenuItem("3", "Agent 基础能力", "第二层"),
                    MenuItem("4", "粮食策略", "第三层"),
                ),
                back_label="退出",
            )
            if choice == "1":
                self.report_menu()
            elif choice == "2":
                self.provider_menu()
            elif choice == "3":
                self.agent_menu()
            elif choice == "4":
                self.food_menu()
            elif choice is None:
                self.menu.clear()
                if not self.menu.interactive:
                    self.output("已退出 Runtime Lab。")
                return

    def report_menu(self) -> None:
        while True:
            breadcrumb = "Runtime Lab / 运行总览与报告"
            choice = self.menu.choose(
                "运行总览与报告",
                (
                    MenuItem("1", "查看当前总览"),
                    MenuItem("2", "重新生成验证报告"),
                    MenuItem("3", "查看历史报告"),
                ),
                breadcrumb=breadcrumb,
                back_label="返回上层",
            )
            if choice is None:
                return
            if choice == "1":
                self._action("当前运行总览", breadcrumb, self._show_current_overview)
            elif choice == "2":
                self._action("重新生成验证报告", breadcrumb, self._regenerate_overview)
            elif choice == "3":
                self._overview_history_menu()

    def provider_menu(self) -> None:
        while True:
            breadcrumb = "Runtime Lab / 第一层"
            configured = configured_provider_ids(self.config)
            items = [MenuItem("1", "Provider × 模型概览表")]
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
            items.append(MenuItem(add_key, "添加或配置其他 Provider"))
            choice = self.menu.choose(
                "Provider 与原始模型",
                tuple(items),
                breadcrumb=breadcrumb,
                back_label="返回上层",
            )
            if choice is None:
                return
            if choice == "1":
                self._action(
                    "Provider × 模型概览表",
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
            breadcrumb = f"Runtime Lab / 第一层 / {provider_id}"
            choice = self.menu.choose(
                self._provider_label(provider_id),
                (
                    MenuItem("1", "查看配置与状态"),
                    MenuItem("2", "修改配置"),
                    MenuItem("3", "验证连通性"),
                    MenuItem("4", "更新模型列表"),
                    MenuItem("5", "编辑手工模型目录"),
                    MenuItem("6", "批量验证所有模型"),
                    MenuItem("7", "查看模型验证结果"),
                ),
                breadcrumb=breadcrumb,
                back_label="返回 Provider 列表",
            )
            if choice is None:
                return
            if choice == "1":
                self._action(
                    f"{provider_id} 配置与状态",
                    breadcrumb,
                    lambda provider_id=provider_id: self._show_provider(provider_id),
                )
            elif choice == "2":
                self._action(
                    f"配置 Provider：{provider_id}",
                    breadcrumb,
                    lambda provider_id=provider_id: self._configure_provider(
                        provider_id
                    ),
                )
            elif choice == "3":
                self._action(
                    f"验证 Provider：{provider_id}",
                    breadcrumb,
                    lambda provider_id=provider_id: self._print_result(
                        ProviderValidationRunner(self.config).verify_provider(
                            provider_id
                        )
                    ),
                )
            elif choice == "4":
                self._action(
                    f"更新模型列表：{provider_id}",
                    breadcrumb,
                    lambda provider_id=provider_id: self._update_provider_models(
                        provider_id
                    ),
                )
            elif choice == "5":
                self._action(
                    f"编辑手工模型目录：{provider_id}",
                    breadcrumb,
                    lambda provider_id=provider_id: self._edit_manual_models(
                        provider_id
                    ),
                )
            elif choice == "6":
                self._action(
                    f"批量验证：{provider_id}",
                    breadcrumb,
                    lambda provider_id=provider_id: self._batch_verify_models(
                        provider_id
                    ),
                )
            elif choice == "7":
                self._action(
                    f"{provider_id} 模型验证结果",
                    breadcrumb,
                    lambda provider_id=provider_id: self._show_provider_evidence(
                        provider_id
                    ),
                )

    def agent_menu(self) -> None:
        while True:
            breadcrumb = "Runtime Lab / 第二层"
            choice = self.menu.choose(
                "Agent 基础能力",
                (
                    MenuItem("1", "查看工具配置"),
                    MenuItem("2", "配置基础工具"),
                    MenuItem("3", "验证全部本地工具"),
                    MenuItem("4", "验证网络搜索工具"),
                    MenuItem("5", "验证模型 + Agent 工具调用"),
                ),
                breadcrumb=breadcrumb,
                back_label="返回上层",
            )
            if choice is None:
                return
            if choice == "1":
                self._action("工具配置", breadcrumb, self._show_tool_configs)
            elif choice == "2":
                self._configure_tool_menu()
            elif choice == "3":
                self._action(
                    "本地工具验证",
                    breadcrumb,
                    lambda: self._print_suite(
                        DirectToolValidationRunner(self.config).run()
                    ),
                )
            elif choice == "4":
                self._action("网络搜索验证", breadcrumb, self._verify_web_search)
            elif choice == "5":
                self._action("模型 + Agent 验证", breadcrumb, self._verify_model_agent)

    def food_menu(self) -> None:
        store = FoodCatalogStore()
        while True:
            breadcrumb = "Runtime Lab / 第三层"
            choice = self.menu.choose(
                "粮食策略",
                (
                    MenuItem("1", "查看当前粮食策略"),
                    MenuItem("2", "自动更新粮食策略"),
                    MenuItem("3", "验证当前粮食策略"),
                    MenuItem("4", "历史版本与回滚"),
                ),
                breadcrumb=breadcrumb,
                back_label="返回上层",
            )
            if choice is None:
                return
            if choice == "1":
                self._food_strategy_menu(store)
            elif choice == "2":
                self._action(
                    "自动更新粮食策略",
                    breadcrumb,
                    lambda: self._update_foods(store),
                )
            elif choice == "3":
                self._action(
                    "验证当前粮食配置",
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
        self.output(f"报告已保存: {path}")
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
            self.output(f"操作失败：{exc}")
            return None
        finally:
            if result is not False:
                self.menu.pause()

    def _show_current_overview(self) -> None:
        store = RuntimeOverviewStore()
        report = store.load_current()
        if report is None:
            self.output("尚无历史验证报告，以下为当前本地配置快照。")
            report = RuntimeOverviewGenerator(self.config).snapshot()
        self._render_overview(report)

    def _regenerate_overview(self) -> None:
        providers = configured_provider_ids(self.config)
        if not providers:
            self.output("尚无已配置 Provider，无法生成验证报告。")
            return
        self.output(f"即将验证 {len(providers)} 个已配置 Provider 及其全部模型：")
        for provider_id in providers:
            self.output(f"- {provider_id}")
        self.output("真实模型调用可能产生费用。")
        if self.input("确认重新生成报告吗？[y/N]: ").strip().lower() != "y":
            self.output("已取消。")
            return
        report = RuntimeOverviewGenerator(self.config).regenerate()
        path = RuntimeOverviewStore().save(report)
        self._render_overview(report)
        self.output(f"\n报告已保存：{path}")

    def _render_overview(self, report: dict[str, Any]) -> None:
        summary = report.get("summary", {})
        self.output(f"报告时间：{report.get('created_at', '未知')}")
        self.output(
            "Provider："
            f"已配置 {summary.get('configured_providers', 0)}，"
            f"连接通过 {summary.get('reachable_providers', 0)}"
        )
        self.output(
            "模型入口："
            f"共 {summary.get('model_endpoints', 0)}，"
            f"验证通过 {summary.get('verified_model_endpoints', 0)}，"
            f"Agent 通过 {summary.get('agent_verified_models', 0)}"
        )
        self.output(
            "粮食："
            f"可用 {summary.get('available_foods', 0)} / "
            f"{summary.get('total_foods', 0)}"
        )
        self.output("\nProvider 状态：")
        for provider in report.get("providers", ()):
            if not isinstance(provider, dict):
                continue
            status = {
                "passed": "✓",
                "failed": "✗",
                "unknown": "?",
            }.get(str(provider.get("status")), "?")
            self.output(
                f"- {status} {provider.get('id')}: {provider.get('api_base', '')}"
            )
        self.output("\nProvider × 模型：")
        width = shutil.get_terminal_size(fallback=(100, 30)).columns
        for line in render_provider_model_matrix(report, width=width):
            self.output(line)
        generation_note = report.get("food_generation_note")
        if generation_note:
            self.output(f"\n粮食生成来源：{generation_note}")

    def _overview_history_menu(self) -> None:
        store = RuntimeOverviewStore()
        versions = store.history()
        if not versions:
            self._action(
                "历史报告",
                "Runtime Lab / 运行总览与报告",
                lambda: self.output("尚无历史报告。"),
            )
            return
        while True:
            selected = self.menu.choose(
                "历史报告",
                tuple(
                    MenuItem(str(index), path.stem.removeprefix("runtime-overview-"))
                    for index, path in enumerate(versions, 1)
                ),
                breadcrumb="Runtime Lab / 运行总览与报告 / 历史报告",
                back_label="返回",
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
                    "Runtime Lab / 运行总览与报告 / 历史报告",
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
            return "已配置 / 未验证"
        return {
            "passed": "已配置 / 连接通过",
            "failed": "已配置 / 连接失败",
        }.get(str(provider.get("status")), "已配置 / 未验证")

    def _provider_label(self, provider_id: str) -> str:
        provider = self.config.providers.get(provider_id, {})
        display_name = str(provider.get("display_name", "")).strip()
        return f"{display_name} ({provider_id})" if display_name else provider_id

    def _show_provider_model_matrix(self) -> None:
        report = RuntimeOverviewStore().load_current()
        if report is None:
            report = RuntimeOverviewGenerator(self.config).snapshot()
            self.output("当前没有正式报告，以下根据本地模型证据展示。\n")
        width = shutil.get_terminal_size(fallback=(100, 30)).columns
        for line in render_provider_model_matrix(report, width=width):
            self.output(line)

    def _show_provider(self, provider_id: str) -> None:
        provider = self.config.providers.get(provider_id, {})
        self.output(f"Provider：{provider_id}")
        if provider.get("display_name"):
            self.output(f"名称：{provider['display_name']}")
        self.output(f"API Base：{provider.get('api_base', '')}")
        self.output(f"API 模式：{provider.get('api_mode', '')}")
        self.output(f"认证方式：{provider.get('auth_type', '')}")
        self.output(f"密钥：{'已配置' if provider.get('api_key') else '未配置'}")
        self.output(f"配置状态：{provider.get('status', 'unknown')}")
        specs = configured_model_specs(provider)
        self.output("模型目录：")
        for item in specs:
            capabilities = known_capabilities(item.model_id, item.display_name)
            ability = (
                f" [已知能力：{_format_capabilities(capabilities)}]"
                if capabilities
                else " [已知能力：待识别]"
            )
            self.output(f"- {item.display_name}: {item.model_id}{ability}")
        if not specs:
            self.output("- 未配置")
        self.output("注意：配置状态不等于实时连通状态，请执行“验证连通性”。")

    def _show_provider_evidence(self, provider_id: str) -> None:
        evidence = [
            item
            for item in ModelEvidenceStore().load().values()
            if item.model.startswith(f"{provider_id}/")
        ]
        if not evidence:
            self.output("该 Provider 尚无模型验证记录。")
            return
        for item in evidence:
            status = "✓" if item.verified else "✗"
            latency = f"{item.latency_ms:.0f}ms" if item.latency_ms else "—"
            label = item.display_name or item.model
            ability = _format_capabilities(item.capabilities)
            self.output(
                f"- {status} {label} [{item.model}]: {latency} "
                f"· 已知能力：{ability}"
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
        items.append(MenuItem(custom_key, "新增 Custom Provider", "可重复添加"))
        selected = self.menu.choose(
            "添加或配置其他 Provider",
            tuple(items),
            breadcrumb="Runtime Lab / 第一层 / 添加 Provider",
            back_label="返回",
        )
        if selected is None:
            return
        if selected == custom_key:
            self._action(
                "新增 Custom Provider",
                "Runtime Lab / 第一层 / 添加 Provider",
                self._create_custom_provider,
            )
            return
        provider_id = builtin_by_key.get(selected)
        if provider_id is None:
            return
        self._action(
            f"配置 Provider：{provider_id}",
            "Runtime Lab / 第一层 / 添加 Provider",
            lambda: self._configure_provider(provider_id),
        )

    def _verify_web_search(self) -> None:
        warning = self.input("将访问网络，继续吗？[y/N]: ").strip().lower()
        if warning == "y":
            self._print_result(
                DirectToolValidationRunner(self.config).verify_web_search()
            )
        else:
            self.output("已取消。")

    def _show_tool_configs(self) -> None:
        configs = load_tool_configs(self.config.runtime_policy)
        labels = {
            "web_search": "网络搜索",
            "local_file": "本地文件",
            "code_sandbox": "代码沙箱",
            "skills_evolution": "技能进化",
        }
        for key in TOOL_KEYS:
            item = configs[key]
            status = "已启用" if item.get("enabled") else "已停用"
            detail = ""
            if key == "web_search":
                detail = f" / {item.get('provider', 'duckduckgo')} / 密钥{'已配置' if item.get('api_key') else '未配置'}"
            elif key == "local_file":
                detail = f" / {item.get('root', '')}"
            elif key == "code_sandbox":
                detail = f" / {item.get('timeout_seconds', 5)}s"
            self.output(f"- {labels[key]}: {status}{detail}")

    def _configure_tool_menu(self) -> None:
        labels = {
            "web_search": "网络搜索",
            "local_file": "本地文件",
            "code_sandbox": "代码沙箱",
            "skills_evolution": "技能进化",
        }
        choice = self.menu.choose(
            "配置基础工具",
            tuple(
                MenuItem(str(index), labels[key])
                for index, key in enumerate(TOOL_KEYS, 1)
            ),
            breadcrumb="Runtime Lab / 第二层 / 配置工具",
            back_label="返回上层",
        )
        if choice is None:
            return
        tool_key = TOOL_KEYS[int(choice) - 1]
        self._action(
            f"配置{labels[tool_key]}",
            "Runtime Lab / 第二层 / 配置工具",
            lambda: self._configure_tool(tool_key),
        )

    def _configure_tool(self, tool_key: str) -> bool:
        configs = load_tool_configs(self.config.runtime_policy)
        current = dict(configs[tool_key])
        enabled = self.menu.read_text(
            f"是否启用 [y/n] [{'y' if current.get('enabled') else 'n'}]: ",
            default="y" if current.get("enabled") else "n",
        )
        if enabled is None:
            return False
        current["enabled"] = enabled.lower() == "y"
        pending_secret: str | None = None
        if tool_key == "web_search":
            provider = self.menu.read_text(
                "搜索 Provider [duckduckgo/brave/tavily]: ",
                default=str(current.get("provider") or "duckduckgo"),
            )
            if provider is None or provider not in {"duckduckgo", "brave", "tavily"}:
                self.output("已取消或 Provider 无效。")
                return False
            current["provider"] = provider
            api_base = self.menu.read_text(
                "API Base（空值使用 Provider 默认）: ",
                default=str(current.get("api_base") or ""),
            )
            if api_base is None:
                return False
            current["api_base"] = api_base
            api_key = self.menu.read_text(
                "API Key（空值保留，- 清除，Esc 取消）: ",
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
                "默认结果数 [1-10]: ",
                default=str(current.get("max_results") or 3),
            )
            if count is None:
                return False
            current["max_results"] = max(1, min(int(count), 10))
            current.pop("api_key", None)
        elif tool_key == "local_file":
            root = self.menu.read_text(
                "允许访问的本地根目录: ", default=str(current.get("root") or "")
            )
            if root is None or not root:
                return False
            current["root"] = root
        elif tool_key == "code_sandbox":
            timeout = self.menu.read_text(
                "超时秒数 [1-60]: ",
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
        self.output("工具配置已安全保存到本地。")
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
                    else "未配置"
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
                "当前粮食策略",
                tuple(items),
                breadcrumb="Runtime Lab / 第三层 / 当前粮食策略",
                back_label="返回",
            )
            if selected is None:
                return
            if not selected.isdigit() or not 1 <= int(selected) <= len(keys):
                continue
            food_key = keys[int(selected) - 1]
            self._action(
                FIXED_FOOD_KINDS[food_key].display_name,
                "Runtime Lab / 第三层 / 当前粮食策略",
                lambda food_key=food_key: self._show_food_detail(store, food_key),
            )

    def _show_food_detail(self, store: FoodCatalogStore, food_key: str) -> None:
        catalog = store.load()
        recipe = catalog.recipes.get(food_key)
        if recipe is None:
            self.output("该粮食尚未配置。")
            return
        self.output(f"主模型：{recipe.primary.model or '未配置'}")
        self.output(f"推理档位：{recipe.primary.reasoning_profile.value}")
        self.output(f"深度模型：{recipe.deep.model if recipe.deep else '—'}")
        self.output(f"验证模型：{recipe.verifier.model if recipe.verifier else '—'}")
        fallbacks = ", ".join(item.model for item in recipe.technical_fallbacks)
        self.output(f"技术备用：{fallbacks or '—'}")
        self.output(f"最大输出：{recipe.primary.max_tokens}")
        self.output(f"温度：{recipe.primary.temperature}")
        self.output(f"工具：{', '.join(recipe.primary.tools) or '无'}")
        self.output(f"状态：{recipe.validation_status.value}")
        self.output(f"来源：{recipe.source}")
        if catalog.generation_note:
            self.output(f"版本生成方式：{catalog.generation_note}")

    def _food_history_menu(self, store: FoodCatalogStore) -> None:
        versions = store.history_versions()
        if not versions:
            self._action(
                "历史版本与回滚",
                "Runtime Lab / 第三层",
                lambda: self.output("尚无粮食历史版本。"),
            )
            return
        while True:
            selected = self.menu.choose(
                "历史版本与回滚",
                tuple(
                    MenuItem(str(index), path.stem.removeprefix("foods-"))
                    for index, path in enumerate(versions, 1)
                ),
                breadcrumb="Runtime Lab / 第三层 / 历史版本",
                back_label="返回",
            )
            if selected is None:
                return
            if not selected.isdigit() or not 1 <= int(selected) <= len(versions):
                continue
            path = versions[int(selected) - 1]
            self._action(
                path.name,
                "Runtime Lab / 第三层 / 历史版本",
                lambda path=path: self._show_food_history_version(store, path),
            )

    def _show_food_history_version(self, store: FoodCatalogStore, path: Path) -> None:
        catalog = FoodCatalog.from_dict(read_yaml_mapping(path))
        self.output(f"版本：{catalog.version}")
        self.output(f"生成时间：{catalog.generated_at or '未知'}")
        self.output(f"生成方式：{catalog.generation_note or '旧版本未记录'}")
        for key, kind in FIXED_FOOD_KINDS.items():
            recipe = catalog.recipes.get(key)
            self.output(
                f"- {kind.display_name}: "
                f"{recipe.primary.model if recipe and recipe.primary.model else '未配置'}"
            )
        if self.input("恢复这个版本吗？[y/N]: ").strip().lower() == "y":
            restored = store.restore_version(path)
            self.output(f"已恢复粮食版本 {restored.version}。")

    def _update_foods(self, store: FoodCatalogStore) -> None:
        evidence = list(ModelEvidenceStore().load().values())
        if not evidence:
            self.output("尚无模型验证证据，请先在第一层批量验证模型。")
            return
        planning_model = select_planning_model(self.config, evidence)
        planner = (
            FoodPlanner(LLMFoodPlanningAdvisor(self.config, planning_model))
            if planning_model
            else FoodPlanner()
        )
        if planning_model:
            self.output(f"尝试使用规划模型生成粮食建议: {planning_model}")
        else:
            self.output("没有可用规划模型，将使用确定性规则生成。")
        current_catalog = store.load()
        proposal = planner.propose(evidence, current_catalog)
        if proposal.generation_sources == ("model", "rules"):
            self.output("生成来源：模型建议 + 确定性规则校验")
        elif proposal.advisor_error:
            self.output(f"规划模型调用失败：{proposal.advisor_error}")
            self.output("生成来源：确定性规则（模型不可用时自动降级）")
        else:
            self.output("生成来源：确定性规则（当前没有可用规划模型）")
        changed = [item for item in proposal.changes if item.change_type != "unchanged"]
        unchanged_count = len(proposal.changes) - len(changed)
        self.output("\n粮食更新预览")
        self.output("─" * 48)
        self.output(
            f"计划修改 {len(changed)} 种粮食，保持不变 {unchanged_count} 种。"
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
                self.output(f"  警告: {warning}")
        if not proposal.has_changes:
            self.output("当前粮食已经是最新配置。")
            return
        self.output("\n未确认前不会写入配置或生成新版本。")
        if self.menu.confirm("确认应用以上粮食更新吗？"):
            store.save(proposal.catalog)
            self.output("粮食更新已应用，并保留了旧版本。")
            if proposal.generation_sources == ("model", "rules"):
                self.output("本次粮食策略由模型建议与确定性规则共同生成。")
            elif proposal.advisor_error:
                self.output("本次规划模型不可用，粮食策略已由确定性规则生成。")
            else:
                self.output("本次粮食策略由确定性规则生成。")
        else:
            self.output("未应用更新。")

    @staticmethod
    def _food_recipe_diff(old_recipe, new_recipe) -> list[tuple[str, str, str]]:
        def values(recipe) -> dict[str, str]:
            if recipe is None:
                return {}
            return {
                "主模型": recipe.primary.model or "不可用",
                "推理档位": recipe.primary.reasoning_profile.value,
                "最大输出": str(recipe.primary.max_tokens),
                "温度": str(recipe.primary.temperature),
                "工具": ", ".join(recipe.primary.tools) or "无",
                "深度模型": recipe.deep.model if recipe.deep else "无",
                "验证模型": recipe.verifier.model if recipe.verifier else "无",
                "技术备用": (
                    ", ".join(item.model for item in recipe.technical_fallbacks)
                    or "无"
                ),
                "验证状态": recipe.validation_status.value,
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
            self.output("当前粮食策略没有可调用的模型，请先自动更新粮食策略。")
            return
        model_count = sum(len(models) for models in referenced.values())
        self.output(
            f"将真实调用粮食策略引用的 {model_count} 个模型后再验证，"
            "云端模型可能产生费用。"
        )
        if not self.menu.confirm(
            "确认开始粮食集成验证吗？",
            accept_label="开始验证",
            reject_label="取消",
        ):
            self.output("已取消，未生成伪失败报告。")
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
                        display_name=canonical_display_name(
                            result.model, display_name
                        ),
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
        self.output(f"粮食验证报告已保存: {path}")

    @staticmethod
    def _food_referenced_models(catalog: FoodCatalog) -> dict[str, list[str]]:
        """收集配方实际引用的模型，按 Provider 去重，空占位不参与调用。"""
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
        is_custom = provider_id not in BUILTIN_PROFILES or provider_id == "custom_openai"
        if is_custom:
            display_name = self.menu.read_text(
                f"Provider 名称 [{provider.get('display_name', '')}]: ",
                default=str(provider.get("display_name", "")),
            )
            if display_name is None:
                self.output("已取消，配置未修改。")
                return False
            if not display_name:
                self.output("Provider 名称不能为空，配置未修改。")
                return False
            provider["display_name"] = display_name
        current_base = str(provider.get("api_base") or profile.api_base)
        api_base = self.menu.read_text(
            f"API Base [{current_base}]: ", default=current_base
        )
        if api_base is None:
            self.output("已取消，配置未修改。")
            return False
        provider["api_base"] = api_base
        provider["api_mode"] = str(provider.get("api_mode") or profile.api_mode)
        provider["auth_type"] = str(provider.get("auth_type") or profile.auth_type)
        pending_secret: str | None = None
        if provider["auth_type"] != "none" or is_custom:
            api_key = self.menu.read_text(
                "API Key（空值保留原值，输入 - 清除，Esc 取消）: ",
                masked=True,
                line_input=self.secret_input,
            )
            if api_key is None:
                self.output("已取消，配置未修改。")
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
            provider["api_key_env"] = provider.get("api_key_env") or profile.api_key_env_var
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
            self.output("已取消，配置未修改。")
            return False
        self._set_provider_specs(provider, specs)
        self._commit_provider(provider_id, provider, pending_secret)
        self.output("Provider 配置已安全保存到本地。")
        if provider_id == "ollama":
            self.output(
                "提示：这里只配置 Ollama 地址。模型需继续完成“批量验证”，"
                "并在第三层生成/更新粮食后才会进入新路由。"
            )
        return True

    def _create_custom_provider(self) -> bool:
        display_name = self.menu.read_text("Provider 名称（Esc 取消）: ")
        if display_name is None:
            self.output("已取消，未创建 Provider。")
            return False
        if not display_name:
            self.output("Provider 名称不能为空，未创建。")
            return False
        provider_id = self._next_custom_provider_id(display_name)
        template = BUILTIN_PROFILES["custom_openai"]
        api_base = self.menu.read_text(
            f"API Base [{template.api_base}]: ", default=template.api_base
        )
        if api_base is None:
            self.output("已取消，未创建 Provider。")
            return False
        api_key = self.menu.read_text(
            "API Key（可选，Esc 取消）: ",
            masked=True,
            line_input=self.secret_input,
        )
        if api_key is None:
            self.output("已取消，未创建 Provider。")
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
            self.output("未配置可用模型，未创建 Provider。")
            return False
        self._set_provider_specs(provider, specs)
        self._commit_provider(provider_id, provider, api_key if api_key else None)
        self.output(f"已创建 Custom Provider：{display_name} ({provider_id})")
        return True

    def _refresh_specs_after_configuration(
        self,
        provider_id: str,
        provider: dict[str, Any],
        *,
        existing_specs: tuple[ProviderModelSpec, ...] | list[ProviderModelSpec],
        is_new: bool,
    ) -> list[ProviderModelSpec] | None:
        self.output("正在自动拉取模型列表…")
        try:
            specs = self._auto_discover_model_specs(provider_id, provider)
        except Exception as exc:
            self.output(f"自动拉取失败：{exc}")
        else:
            if specs:
                self.output(f"已自动更新 {len(specs)} 个模型。")
                return specs
            self.output("自动拉取未返回任何模型。")

        defaults = list(existing_specs) or [
            ProviderModelSpec(model_id, model_id)
            for model_id in suggested_model_names(str(provider.get("api_base", "")))
        ]
        if existing_specs and not is_new:
            edit = self.menu.read_text(
                "将保留当前模型目录，是否现在手工编辑？[y/N]: ",
                default="n",
            )
            if edit is None:
                return None
            if edit.lower() != "y":
                self.output("自动更新失败，已保留原模型目录。")
                return list(existing_specs)
        else:
            self.output("请至少手工配置一个模型后继续。")
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
                f"模型 {index + 1} ID"
                f" [{default.model_id if default else ''}]: ",
                default=default.model_id if default else "",
            )
            if model_id is None:
                return None
            if not model_id:
                self.output("模型 ID 不能为空。")
                return None
            display_default = default.display_name if default else model_id
            display_name = self.menu.read_text(
                f"显示名称 [{display_default}]: ", default=display_default
            )
            if display_name is None:
                return None
            specs.append(ProviderModelSpec(model_id, display_name or model_id))
            has_more_defaults = index + 1 < len(defaults)
            more_default = "y" if has_more_defaults else "n"
            more = self.menu.read_text(
                "继续下一个模型？[Y/n]: "
                if has_more_defaults
                else "继续添加模型？[y/N]: ",
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
            {"id": item.model_id, "display_name": item.display_name}
            for item in specs
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
        self.output("正在基于当前 Provider 配置更新模型列表…")
        try:
            specs = self._auto_discover_model_specs(provider_id, provider)
            if not specs:
                raise RuntimeError("Provider 未返回任何模型")
        except Exception as exc:
            self.output(f"自动更新失败：{exc}")
            edit = self.menu.read_text(
                "是否编辑手工模型目录？[y/N]: ", default="n"
            )
            if edit is None or edit.lower() != "y":
                self.output("已保留当前模型目录。")
                return False
            specs = self._prompt_manual_model_specs(existing)
            if not specs:
                self.output("未修改模型目录。")
                return False
        if not specs:
            self.output("Provider 未返回任何模型，已保留原目录。")
            return False
        self._set_provider_specs(provider, specs)
        self._commit_provider(provider_id, provider, None)
        self.output(f"模型目录已更新，共 {len(specs)} 个模型：")
        for item in specs:
            self.output(f"- {item.display_name}: {item.model_id}")
        return True

    def _edit_manual_models(self, provider_id: str) -> bool:
        provider = copy.deepcopy(self.config.providers.get(provider_id, {}))
        specs = self._prompt_manual_model_specs(configured_model_specs(provider))
        if not specs:
            self.output("未修改模型目录。")
            return False
        self._set_provider_specs(provider, specs)
        self._commit_provider(provider_id, provider, None)
        self.output(f"手工模型目录已保存，共 {len(specs)} 个模型。")
        return True

    def _batch_verify_models(self, provider_id: str) -> None:
        try:
            models = discover_provider_models(provider_id, self.config)
        except Exception as exc:
            self.output(f"模型发现失败: {exc}")
            return
        if not models:
            self.output("没有可验证模型。")
            return
        if all(model.source == "configured" for model in models):
            self.output("未能自动拉取模型，将验证手工配置的模型 ID。")
        self.output(f"即将真实调用 {len(models)} 个模型，可能产生费用。")
        if self.input("继续批量验证吗？[y/N]: ").strip().lower() != "y":
            self.output("已取消。")
            return
        suite = ProviderValidationRunner(self.config).verify_models(
            provider_id, [model.name for model in models]
        )
        self._print_suite(suite)
        evidence = []
        model_by_id = {model.name: model for model in models}
        for result in suite.results:
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
        self.output(f"验证证据和报告已保存: {path}")
        self.output("下一步：进入第三层生成/更新粮食，验证模型才会正式进入路由。")

    def _verify_model_agent(self) -> None:
        store = ModelEvidenceStore()
        available = sorted(
            (item for item in store.load().values() if item.verified),
            key=lambda item: (item.display_name or item.model, item.model),
        )
        if not available:
            self.output("尚无已验证模型，请先在第一层批量验证模型。")
            return
        model_by_key: dict[str, ModelEvidence] = {}
        items = [MenuItem("1", "验证所有可用模型", f"共 {len(available)} 个")]
        for index, item in enumerate(available, 2):
            key = str(index)
            model_by_key[key] = item
            label = item.display_name or item.model
            items.append(MenuItem(key, label, item.model))
        choice = self.menu.choose(
            "选择模型 + Agent 验证范围",
            tuple(items),
            breadcrumb="Runtime Lab / 第二层 / 模型 + Agent 验证",
            back_label="取消",
        )
        if choice is None:
            return
        selected_models = available if choice == "1" else [model_by_key.get(choice)]
        selected_models = [item for item in selected_models if item is not None]
        if not selected_models:
            return
        self.output(
            f"即将真实调用 {len(selected_models)} 个模型，"
            "分别验证代码与本地文件工具，可能产生费用。"
        )
        if not self.menu.confirm(
            "确认开始模型 + Agent 验证吗？",
            accept_label="开始验证",
            reject_label="取消",
        ):
            self.output("已取消。")
            return
        runner = ModelAgentValidationRunner(self.config)
        suites: list[ValidationSuite] = []
        evidence_updates: list[ModelEvidence] = []
        for index, selected in enumerate(selected_models, 1):
            provider, model = selected.model.split("/", 1)
            self.output(
                f"\n[{index}/{len(selected_models)}] "
                f"正在验证 {selected.display_name or selected.model}…"
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
            f"\n模型 + Agent 验证完成：通过 {passed_count} / {len(suites)}。"
        )
        self.output(f"汇总证据和报告已保存: {path}")

    def _print_suite(self, suite: ValidationSuite) -> None:
        self.output(f"\n[{suite.name}] {'通过' if suite.passed else '失败'}")
        for result in suite.results:
            self._print_result(result)

    def _print_result(self, result: Any) -> None:
        icon = {
            CheckStatus.PASSED: "✓",
            CheckStatus.FAILED: "✗",
            CheckStatus.WARNING: "!",
            CheckStatus.SKIPPED: "-",
        }.get(result.status, "-")
        latency = (
            f" ({result.duration_ms:.1f}ms)" if result.duration_ms is not None else ""
        )
        self.output(f"{icon} {result.check_id}: {result.message}{latency}")


def _format_capabilities(capabilities: frozenset[str] | set[str]) -> str:
    labels = {
        "text": "文本",
        "reasoning": "推理",
        "vision": "视觉",
        "audio": "音频",
        "code": "代码",
        "tools": "工具",
    }
    order = ("text", "reasoning", "vision", "audio", "code", "tools")
    known = [labels[item] for item in order if item in capabilities]
    extra = sorted(item for item in capabilities if item not in labels)
    return "/".join((*known, *extra)) or "能力未知"


def main() -> None:
    RuntimeLab().run()
