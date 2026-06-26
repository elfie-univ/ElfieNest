from __future__ import annotations

import urllib.error
import urllib.request

from elfienest.cli.tui.common import (
    clear_screen,
    input_password,
    input_text,
    print_banner,
    print_success_panel,
    print_tui_panel,
    rich_console,
)
from elfienest.config.user_config import (
    read_env_file,
    read_user_config,
    write_env_file,
    write_user_config,
)
from elfienest.operations.setup_service import (
    SetupAlreadyCompleteError,
    create_first_admin_account,
    needs_setup,
)
from elfienest.persistence.store import init_db, migrate_db_if_needed
from runtime.data_home import get_db_path
from runtime.provider_profiles import BUILTIN_PROFILES


def run_setup_wizard() -> None:
    clear_screen()
    print_banner()
    print_tui_panel("ElfieNest Setup Wizard", "首次启动前完成管理员、模型服务商与数据库初始化")

    db_path = str(get_db_path())
    init_db(db_path)
    migrate_db_if_needed(db_path)

    if not needs_setup(db_path):
        print("  ⚠️  系统已初始化，跳过设置向导")
        return

    print("  让我们开始配置你的 ElfieNest 系统...")
    print()

    _print_step("1/4", "创建管理员账号")
    username = input_text("  管理员用户名", "admin") or "admin"
    password = input_text("  管理员密码", "admin123") or "admin123"
    print()

    _print_step("2/4", "配置大模型服务商")
    _print_ollama_status()
    print()

    providers = list(BUILTIN_PROFILES.keys())
    print("  可用服务商:")
    for i, pid in enumerate(providers, 1):
        profile = BUILTIN_PROFILES[pid]
        print(f"    {i}. {pid:12s} - {profile.name}")
    print()

    print("  是否配置其他服务商？(y/N): ", end="")
    try:
        choice = input().strip().lower()
    except KeyboardInterrupt:
        choice = "n"

    if choice == "y":
        _configure_optional_providers(providers)

    print()
    _print_step("3/4", "初始化数据库")

    try:
        create_first_admin_account(db_path, username=username, password=password)
        print(f"  ✅ 管理员 '{username}' 创建成功")
    except SetupAlreadyCompleteError as e:
        print(f"  ⚠️  管理员已存在或创建失败: {e}")

    print()
    _print_step("4/4", "完成设置")
    print_success_panel(
        [
            "设置完成！",
            "启动服务: elfie",
            f"登录信息: {username} / {password}",
        ]
    )


def _print_step(step: str, title: str) -> None:
    console = rich_console()
    if console is None:
        print(f"  【步骤 {step}】{title}")
        print()
        return
    console.print(f"  [bold magenta]步骤 {step}[/] [white]{title}[/]")
    print()


def _print_ollama_status() -> None:
    print("  检测 Ollama...")
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
    except (OSError, TimeoutError, urllib.error.URLError):
        print("  ⚠️  Ollama 未运行，将使用 fallback 模式")
        return
    print("  ✅ Ollama 已运行")


def _configure_optional_providers(providers: list[str]) -> None:
    config = read_user_config()
    env_vars = read_env_file()

    while True:
        print("\n  选择要配置的服务商编号 (输入 0 跳过): ", end="")
        try:
            idx_str = input().strip()
            if idx_str == "0":
                break

            idx = int(idx_str) - 1
        except (KeyboardInterrupt, ValueError):
            break

        if not 0 <= idx < len(providers):
            continue

        provider_id = providers[idx]
        profile = BUILTIN_PROFILES[provider_id]
        if not profile.api_key_env_var:
            print(f"  {profile.name} 无需 API Key")
            continue

        print(f"\n  配置 {profile.name}")
        api_key = input_password("  API Key")
        if not api_key:
            continue

        providers_config = config.setdefault("providers", {})
        providers_config[provider_id] = {
            "api_base": profile.api_base,
            "api_mode": profile.api_mode,
            "status": "active",
        }
        env_vars[profile.api_key_env_var] = api_key
        print("  ✅ 配置已保存")

    write_user_config(config)
    write_env_file(env_vars)
