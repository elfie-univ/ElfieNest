"""管理员账户的本机查询与恢复命令。"""

from __future__ import annotations

import getpass
import sys
import urllib.error
import urllib.request
import warnings
from pathlib import Path
from typing import Final, Optional, Tuple

from elfienest.cli.tui.common import input_password
from elfienest.operations.admin_service import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    AdminAccount,
    AdminNotFoundError,
    AdminSelectionRequiredError,
    AdminServiceError,
    list_admin_accounts,
    reset_admin_password,
)
from elfienest.operations.recovery_lock import (
    RecoveryInProgressError,
    admin_recovery_lock,
)
from elfienest.operations.service_lifecycle import (
    ServiceLifecycleResult,
    start_service,
    stop_service,
)
from elfienest.operations.service_process import http_port_from_command
from runtime.storage.data_home import get_db_path, get_elfie_home

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]


def show_admin_accounts(db_path: Optional[str] = None) -> int:
    """显示当前数据库与管理员账户，不暴露认证秘密。"""
    database_path = db_path or str(get_db_path())
    try:
        accounts = list_admin_accounts(database_path)
    except AdminServiceError as error:
        print(f"  ❌ 无法读取管理员账户: {error}")
        return 1

    print("  👤 管理员账号管理")
    print("  " + "=" * 45)
    print(f"  数据库: {database_path}")
    print()
    if not accounts:
        print("  ⚠️  当前数据库没有管理员账户")
        return 1

    print("  【当前管理员】")
    for account in accounts:
        created_at = account.created_at or "未知"
        print(f"    • {account.username}（创建时间: {created_at}）")
    print()
    return 0


def stop_managed_service() -> ServiceLifecycleResult:
    """精确停止当前项目登记的本地服务。"""
    return stop_service(get_elfie_home(), PROJECT_ROOT)


def start_managed_service(
    command: Optional[Tuple[str, ...]] = None,
) -> ServiceLifecycleResult:
    """启动本地服务并等待 HTTP 健康检查通过。"""
    service_command = command or (
        sys.executable,
        str((PROJECT_ROOT / "scripts" / "serve.py").resolve()),
        "--fallback",
    )
    http_port = http_port_from_command(service_command)
    return start_service(
        get_elfie_home(),
        PROJECT_ROOT,
        command=service_command,
        health_checker=lambda: _web_is_healthy(http_port),
    )


def reset_password_interactive(
    username: Optional[str], db_path: Optional[str] = None
) -> int:
    """通过隐藏输入安全恢复一个现有管理员的密码。"""
    database_path = db_path or str(get_db_path())
    try:
        accounts = list_admin_accounts(database_path)
        selected_username = _select_admin_username(accounts, username)
    except AdminServiceError as error:
        print(f"  ❌ 无法选择管理员账户: {error}")
        return 1

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            first_password = input_password("  输入新密码")
            if first_password is None:
                print("  ❌ 已取消，未执行任何修改")
                return 1
            second_password = input_password("  再次输入新密码")
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("  ❌ 密码输入已中断，未执行任何修改")
        return 1

    if second_password is None:
        print("  ❌ 已取消，未执行任何修改")
        return 1
    if first_password != second_password:
        print("  ❌ 两次输入的密码不一致，未执行任何修改")
        return 1
    if not MIN_PASSWORD_LENGTH <= len(first_password) <= MAX_PASSWORD_LENGTH:
        print(
            f"  ❌ 新密码长度必须为 {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} 个字符"
        )
        return 1

    try:
        with admin_recovery_lock(Path(database_path).resolve().parent):
            stopped, account, reset_error = _reset_password_locked(
                database_path, selected_username, first_password
            )
    except (OSError, RecoveryInProgressError) as error:
        print(f"  ❌ 无法开始管理员恢复: {error}")
        return 1

    if stopped.status not in ("stopped", "already_stopped"):
        print(f"  ❌ 无法安全停止服务: {stopped.error}")
        return 1
    restarted = start_managed_service(stopped.command)
    if reset_error is not None:
        print(f"  ❌ 密码重置失败: {reset_error}")
        if restarted.status != "started":
            print(f"  ❌ 服务恢复失败: {restarted.error}")
        return 1
    if restarted.status != "started":
        print(f"  ❌ 密码已更新，但服务恢复失败: {restarted.error}")
        return 1
    if account is None:
        print("  ❌ 密码重置结果无效")
        return 1

    print(f"  ✅ 管理员 {account.username} 的密码已重置，旧会话已撤销")
    print(f"  数据库: {database_path}")
    return 0


def _reset_password_locked(
    database_path: str, selected_username: str, new_password: str
) -> Tuple[ServiceLifecycleResult, Optional[AdminAccount], Optional[AdminServiceError]]:
    stopped = stop_managed_service()
    if stopped.status not in ("stopped", "already_stopped"):
        return stopped, None, None

    try:
        account = reset_admin_password(
            database_path,
            selected_username,
            new_password,
        )
    except AdminServiceError as error:
        return stopped, None, error
    return stopped, account, None


def run_admin_menu() -> int:
    """运行可从交互主菜单进入的管理员账号管理子菜单。"""
    last_exit_code = 0
    while True:
        print()
        print("  👤 管理员账号管理")
        print("  " + "=" * 45)
        print("    1. 显示当前管理员")
        print("    2. 重置管理员密码")
        print("    0. 返回主菜单")
        try:
            choice = input("  请选择: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1

        if choice == "1":
            last_exit_code = show_admin_accounts()
        elif choice == "2":
            try:
                username = input("  管理员用户名（只有一个管理员时可留空）: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  ❌ 已取消管理员密码重置")
                last_exit_code = 1
                continue
            last_exit_code = reset_password_interactive(username or None)
        elif choice == "0":
            return last_exit_code
        else:
            print("  ❌ 无效选项，请重新选择")


def dispatch_admin(subcommand: Optional[str], username: Optional[str] = None) -> int:
    """分发管理员查询、恢复和交互子菜单。"""
    if subcommand is None:
        return run_admin_menu()
    if subcommand == "show":
        return show_admin_accounts()
    if subcommand == "reset-password":
        return reset_password_interactive(username)
    print(f"  ❌ 未知管理员命令: {subcommand}")
    return 2


def _select_admin_username(
    accounts: Tuple[AdminAccount, ...], username: Optional[str]
) -> str:
    if username is not None:
        for account in accounts:
            if account.username == username:
                return username
        raise AdminNotFoundError(username)
    if not accounts:
        raise AdminNotFoundError(None)
    if len(accounts) > 1:
        raise AdminSelectionRequiredError(
            tuple(account.username for account in accounts)
        )
    return accounts[0].username


def _web_is_healthy(port: int = 8000) -> bool:
    health_url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(health_url, timeout=0.5) as response:
            return response.status == 200
    except (OSError, TimeoutError, urllib.error.URLError):
        return False
