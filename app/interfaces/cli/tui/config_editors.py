from __future__ import annotations

from ai_runtime.lab.menu import MenuItem, TerminalMenu
from app.features.configuration.user_config import UserConfig, write_user_config
from app.interfaces.cli.tui.common import clear_screen, input_text, print_banner


def config_llm(config: UserConfig) -> None:
    while True:
        clear_screen()
        print_banner()
        print("  🤖 大模型与粮食策略")
        print("  " + "=" * 45)
        print()
        print("  精灵不再直接绑定 Provider 和模型。")
        print("  Provider、模型验证和粮食配方请使用 Runtime Lab：")
        print("    .venv/bin/python -m ai_runtime.lab")
        print("\n  1. 修改旧版默认模型（兼容设置）")
        print("  0. 返回")
        try:
            choice = input("\n请选择 [0-1]: ").strip()
        except (KeyboardInterrupt, EOFError):
            return
        if choice == "0" or choice == "":
            return
        if choice == "1":
            llm = config.setdefault("system", {}).setdefault("llm", {})
            current = llm.get("default_cheap_model", "qwen3.5:0.8b")
            value = input_text(f"请输入默认模型 [{current}]: ")
            if value:
                llm["default_cheap_model"] = value
                write_user_config(config)
                print("\n✅ 兼容默认模型已保存；实际调用仍由粮食策略决定。")
                try:
                    input("按回车键继续...")
                except (EOFError, KeyboardInterrupt):
                    return


def config_engine(config: UserConfig) -> None:
    """用方向键编辑引擎参数，并在返回时一次保存。"""
    menu = TerminalMenu(input_fn=input, output_fn=print)
    while True:
        engine = config.setdefault("system", {}).setdefault("engine", {})
        choice = menu.choose(
            "引擎参数",
            (
                MenuItem("1", f"Tick 间隔（秒）：{engine.get('tick_interval_sec', 1.5)}"),
                MenuItem("2", f"房间精灵上限：{engine.get('max_elfies_per_room', 10)}"),
            ),
            breadcrumb="ElfieNest / Config / 应用 / 引擎参数",
            back_label="保存并返回",
        )
        if choice is None:
            write_user_config(config)
            return
        if choice == "1":
            _set_float(
                menu,
                engine,
                "tick_interval_sec",
                "请输入 Tick 间隔（秒）",
                1.5,
                minimum=0.01,
            )
        elif choice == "2":
            _set_int(
                menu,
                engine,
                "max_elfies_per_room",
                "请输入房间精灵上限",
                10,
                minimum=1,
                maximum=32,
            )


def config_security(config: UserConfig) -> None:
    """编辑实际生效的会话和登录限流字段。"""
    menu = TerminalMenu(input_fn=input, output_fn=print)
    while True:
        security = config.setdefault("system", {}).setdefault("security", {})
        rate_limit = security.setdefault("rate_limit", {})
        choice = menu.choose(
            "会话与安全",
            (
                MenuItem("1", f"Session 有效期（天）：{security.get('session_ttl_days', 7)}"),
                MenuItem("2", f"登录失败次数：{rate_limit.get('max_attempts', 5)}"),
                MenuItem("3", f"限流窗口（秒）：{rate_limit.get('window_seconds', 300)}"),
            ),
            breadcrumb="ElfieNest / Config / Owner 与安全",
            back_label="保存并返回",
        )
        if choice is None:
            write_user_config(config)
            return
        if choice == "1":
            _set_int(
                menu,
                security,
                "session_ttl_days",
                "请输入 Session 有效期（天）",
                7,
                minimum=1,
                maximum=90,
            )
        elif choice == "2":
            _set_int(
                menu,
                rate_limit,
                "max_attempts",
                "请输入窗口内允许的失败次数",
                5,
                minimum=1,
                maximum=100,
            )
        elif choice == "3":
            _set_int(
                menu,
                rate_limit,
                "window_seconds",
                "请输入限流窗口（秒）",
                300,
                minimum=1,
                maximum=3600,
            )


def config_adoption(config: UserConfig) -> None:
    """用方向键编辑精灵领养的实际运行时配置。"""
    menu = TerminalMenu(input_fn=input, output_fn=print)
    while True:
        adoption = config.setdefault("system", {}).setdefault("adoption", {})
        allowed = adoption.setdefault("allowed_species_ids", ["dog", "fox"])
        enabled = adoption.setdefault("personality_presets_enabled", {})
        if not enabled:
            enabled.update(dict.fromkeys(_PERSONALITY_PRESETS, True))
        choice = menu.choose(
            "精灵领养",
            (
                MenuItem("1", f"每用户精灵上限：{adoption.get('max_elfies_per_user', 3)}"),
                MenuItem("2", f"允许物种：{', '.join(allowed)}"),
                MenuItem("3", "性格预设开关"),
            ),
            breadcrumb="ElfieNest / Config / 应用 / 精灵领养",
            back_label="保存并返回",
        )
        if choice is None:
            write_user_config(config)
            return
        if choice == "1":
            _set_int(
                menu,
                adoption,
                "max_elfies_per_user",
                "请输入每用户精灵上限",
                3,
                minimum=1,
                maximum=32,
            )
        elif choice == "2":
            _toggle_species_menu(menu, adoption)
        elif choice == "3":
            _toggle_personality_menu(menu, enabled)


_PERSONALITY_PRESETS = ("活泼好动", "安静温顺", "好奇探索", "胆小害羞", "傲娇独立", "完全随机")


def _toggle_species_menu(menu: TerminalMenu, adoption: UserConfig) -> None:
    """切换可领养物种，至少保留一种。"""
    labels = {"dog": "小狗", "fox": "狐狸"}
    while True:
        allowed = adoption.setdefault("allowed_species_ids", ["dog", "fox"])
        choice = menu.choose(
            "允许的精灵物种",
            tuple(
                MenuItem(str(index), f"{labels[key]}：{'启用' if key in allowed else '禁用'}")
                for index, key in enumerate(labels, 1)
            ),
            breadcrumb="ElfieNest / Config / 应用 / 精灵领养 / 物种",
            back_label="返回领养配置",
        )
        if choice is None:
            return
        if choice not in {"1", "2"}:
            continue
        key = tuple(labels)[int(choice) - 1]
        if key in allowed and len(allowed) == 1:
            continue
        if key in allowed:
            allowed.remove(key)
        else:
            allowed.append(key)


def _toggle_personality_menu(menu: TerminalMenu, enabled: UserConfig) -> None:
    """切换可供 Web 领养页使用的性格预设。"""
    while True:
        choice = menu.choose(
            "性格预设开关",
            tuple(
                MenuItem(str(index), f"{name}：{'启用' if enabled.get(name, True) else '禁用'}")
                for index, name in enumerate(_PERSONALITY_PRESETS, 1)
            ),
            breadcrumb="ElfieNest / Config / 应用 / 精灵领养 / 性格",
            back_label="返回领养配置",
        )
        if choice is None:
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(_PERSONALITY_PRESETS):
            continue
        name = _PERSONALITY_PRESETS[int(choice) - 1]
        if sum(bool(value) for value in enabled.values()) == 1 and enabled.get(name, True):
            continue
        enabled[name] = not enabled.get(name, True)


def _set_float(
    menu: TerminalMenu,
    section: UserConfig,
    key: str,
    prompt: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    try:
        raw = menu.read_text(f"{prompt} [{section.get(key, default)}]: ", default=str(default))
        if raw is None:
            return
        value = float(raw)
        if minimum is not None and value < minimum:
            raise ValueError
        if maximum is not None and value > maximum:
            raise ValueError
    except (TypeError, ValueError):
        print("❌ 输入无效")
        return
    section[key] = value


def _set_int(
    menu: TerminalMenu,
    section: UserConfig,
    key: str,
    prompt: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> None:
    try:
        raw = menu.read_text(f"{prompt} [{section.get(key, default)}]: ", default=str(default))
        if raw is None:
            return
        value = int(raw)
        if minimum is not None and value < minimum:
            raise ValueError
        if maximum is not None and value > maximum:
            raise ValueError
    except (TypeError, ValueError):
        print("❌ 输入无效")
        return
    section[key] = value
