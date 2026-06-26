from __future__ import annotations

from elfienest.config.user_config import UserConfig, write_user_config
from elfienest.tui.common import clear_screen, input_text, print_banner
from runtime.providers.profiles import BUILTIN_PROFILES


def config_llm(config: UserConfig) -> None:
    while True:
        clear_screen()
        print_banner()
        print("  🤖 大模型配置")
        print("  " + "=" * 45)

        llm = config.setdefault("system", {}).setdefault("llm", {})

        print(f"  1. 轻量模型: {llm.get('default_cheap_model', 'qwen3.5:0.8b')}")
        print(f"  2. 深度模型: {llm.get('default_deep_model', 'qwen3.5:0.8b')}")
        print(f"  3. 多模态模型: {llm.get('default_multimodal_model', 'qwen2.5:7b')}")
        print(f"  4. 服务商: {llm.get('default_cheap_provider', 'ollama')}")
        print("  0. 保存并返回")
        print()

        try:
            choice = input("请选择 [0-4]: ").strip()
        except KeyboardInterrupt:
            return

        if choice == "0":
            write_user_config(config)
            print("\n✅ 配置已保存")
            input("按回车键继续...")
            break
        if choice == "1":
            value = input_text(
                "请输入轻量模型名称", llm.get("default_cheap_model", "qwen3.5:0.8b")
            )
            if value:
                llm["default_cheap_model"] = value
        elif choice == "2":
            value = input_text(
                "请输入深度模型名称", llm.get("default_deep_model", "qwen3.5:0.8b")
            )
            if value:
                llm["default_deep_model"] = value
        elif choice == "3":
            value = input_text(
                "请输入多模态模型名称",
                llm.get("default_multimodal_model", "qwen2.5:7b"),
            )
            if value:
                llm["default_multimodal_model"] = value
        elif choice == "4":
            _choose_default_provider(llm)


def config_engine(config: UserConfig) -> None:
    while True:
        clear_screen()
        print_banner()
        print("  ⚙️  引擎配置")
        print("  " + "=" * 45)

        engine = config.setdefault("system", {}).setdefault("engine", {})

        print(f"  1. Tick 间隔 (秒): {engine.get('tick_interval_sec', 1.5)}")
        print(
            f"  2. TTS 语音合成: {'启用' if engine.get('tts_enabled', True) else '禁用'}"
        )
        print(f"  3. 房间精灵上限: {engine.get('max_elfies_per_room', 10)}")
        print("  0. 保存并返回")
        print()

        try:
            choice = input("请选择 [0-3]: ").strip()
        except KeyboardInterrupt:
            return

        if choice == "0":
            write_user_config(config)
            print("\n✅ 配置已保存")
            input("按回车键继续...")
            break
        if choice == "1":
            _set_float(engine, "tick_interval_sec", "请输入 Tick 间隔 (秒)", 1.5)
        elif choice == "2":
            engine["tts_enabled"] = not engine.get("tts_enabled", True)
        elif choice == "3":
            _set_int(engine, "max_elfies_per_room", "请输入房间精灵上限", 10)


def config_security(config: UserConfig) -> None:
    while True:
        clear_screen()
        print_banner()
        print("  🔒 安全配置")
        print("  " + "=" * 45)

        security = config.setdefault("system", {}).setdefault("security", {})

        print(f"  1. Session 有效期 (小时): {security.get('session_ttl_hours', 24)}")
        print(f"  2. 速率限制 (次/分钟): {security.get('rate_limit_per_minute', 60)}")
        print("  0. 保存并返回")
        print()

        try:
            choice = input("请选择 [0-2]: ").strip()
        except KeyboardInterrupt:
            return

        if choice == "0":
            write_user_config(config)
            print("\n✅ 配置已保存")
            input("按回车键继续...")
            break
        if choice == "1":
            _set_int(security, "session_ttl_hours", "请输入 Session 有效期 (小时)", 24)
        elif choice == "2":
            _set_int(
                security,
                "rate_limit_per_minute",
                "请输入速率限制 (次/分钟)",
                60,
            )


def config_adoption(config: UserConfig) -> None:
    while True:
        clear_screen()
        print_banner()
        print("  🐾 精灵领养配置")
        print("  " + "=" * 45)

        adoption = config.setdefault("system", {}).setdefault("adoption", {})

        print(f"  1. 每用户精灵上限: {adoption.get('max_elfies_per_user', 3)}")
        print(
            f"  2. 默认性格风格: {adoption.get('default_personality_style', '活泼好动')}"
        )
        print("  0. 保存并返回")
        print()

        try:
            choice = input("请选择 [0-2]: ").strip()
        except KeyboardInterrupt:
            return

        if choice == "0":
            write_user_config(config)
            print("\n✅ 配置已保存")
            input("按回车键继续...")
            break
        if choice == "1":
            _set_int(adoption, "max_elfies_per_user", "请输入每用户精灵上限", 3)
        elif choice == "2":
            _choose_personality_style(adoption)


def _choose_default_provider(llm: UserConfig) -> None:
    providers = list(BUILTIN_PROFILES.keys())
    print("\n可用服务商:")
    for i, pid in enumerate(providers, 1):
        profile = BUILTIN_PROFILES[pid]
        print(f"  {i}. {pid:12s} - {profile.name}")
    try:
        idx = int(input(f"请选择 [1-{len(providers)}]: ")) - 1
    except (KeyboardInterrupt, ValueError):
        return
    if 0 <= idx < len(providers):
        provider_id = providers[idx]
        llm["default_cheap_provider"] = provider_id
        llm["default_deep_provider"] = provider_id


def _choose_personality_style(adoption: UserConfig) -> None:
    styles = ["活泼好动", "温顺乖巧", "高冷傲娇", "憨厚老实", "机灵古怪"]
    print("\n可用性格风格:")
    for i, style in enumerate(styles, 1):
        print(f"  {i}. {style}")
    try:
        idx = int(input("请选择 [1-5]: ")) - 1
    except (KeyboardInterrupt, ValueError):
        return
    if 0 <= idx < len(styles):
        adoption["default_personality_style"] = styles[idx]


def _set_float(
    section: UserConfig,
    key: str,
    prompt: str,
    default: float,
) -> None:
    try:
        value = float(input_text(prompt, str(section.get(key, default))))
    except (TypeError, ValueError):
        print("❌ 输入无效")
        return
    section[key] = value


def _set_int(
    section: UserConfig,
    key: str,
    prompt: str,
    default: int,
) -> None:
    try:
        value = int(input_text(prompt, str(section.get(key, default))))
    except (TypeError, ValueError):
        print("❌ 输入无效")
        return
    section[key] = value
