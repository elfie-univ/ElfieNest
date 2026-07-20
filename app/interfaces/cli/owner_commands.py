"""本机 Owner 账号菜单。"""

from __future__ import annotations

import getpass
import warnings
from pathlib import Path
from typing import Optional

from app.interfaces.cli.tui.common import input_password, input_text
from app.features.administration.owner_service import (
    MAX_OWNER_PASSWORD_LENGTH,
    MIN_OWNER_PASSWORD_LENGTH,
    OwnerServiceError,
    get_owner_account,
    recover_owner_account,
)
from app.orchestration.lifecycle.recovery_lock import (
    RecoveryInProgressError,
    owner_recovery_lock,
)
from ai_runtime.lab.menu import MenuItem, TerminalMenu
from ai_runtime.storage.data_home import get_db_path


def show_owner_account(db_path: Optional[str] = None) -> int:
    """显示 Owner 登录信息和时间信息，不显示可恢复的密码。"""
    path = db_path or str(get_db_path())
    try:
        account = get_owner_account(path)
    except OwnerServiceError as error:
        print(f"  ❌ 无法读取 Owner 账户: {error}")
        return 1
    print("  👤 Owner 账户信息")
    print("  " + "=" * 45)
    print(f"  User ID: {account.user_id}")
    print(f"  登录名: {account.username}")
    print(f"  密码状态: {account.password_status}")
    print(f"  创建时间: {account.created_at or '未知'}")
    print(f"  最后修改: {account.updated_at or '未知'}")
    print()
    return 0


def show_owner_account_page(
    menu: TerminalMenu,
    db_path: Optional[str] = None,
) -> int:
    """显示 Owner 账号详情页，并等待用户返回。"""
    menu.action_header("Owner 账号信息", "ElfieNest / Owner / 查看账号")
    exit_code = show_owner_account(db_path)
    menu.pause("按 Enter、← 或 Esc 返回 Owner 菜单…")
    return exit_code


def recover_owner_interactive(
    db_path: Optional[str] = None,
    *,
    menu: TerminalMenu | None = None,
) -> int:
    """交互式同时恢复 Owner 登录名和密码。"""
    owner_menu = menu or TerminalMenu(input_fn=input, output_fn=print)
    if menu is not None:
        owner_menu.action_header("恢复 Owner 账号", "ElfieNest / Owner / 恢复账号")
        print("  此操作会同时修改 Owner 登录名和密码，并撤销旧会话。")
        print("  可按 Esc、← 或选择返回取消。")
        print()
        if not owner_menu.confirm(
            "是否开始恢复？",
            accept_label="开始恢复",
            reject_label="返回",
        ):
            print("  已取消，未执行任何修改")
            return 1

    path = db_path or str(get_db_path())
    if not Path(path).expanduser().is_file():
        print(f"  ❌ 无法恢复 Owner: 数据库不存在 ({Path(path).expanduser()})")
        return 1
    if menu is None:
        username = input_text("  新 Owner 登录名")
    else:
        username = owner_menu.read_text("  新 Owner 登录名（Esc 取消）: ")
    if not username:
        print("  ❌ 已取消，未执行任何修改")
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            if menu is None:
                first = input_password("  新 Owner 密码")
                second = input_password("  再次输入新 Owner 密码")
            else:
                first = owner_menu.read_text(
                    "  新 Owner 密码（Esc 取消）: ",
                    masked=True,
                )
                second = owner_menu.read_text(
                    "  再次输入新 Owner 密码（Esc 取消）: ",
                    masked=True,
                )
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("  ❌ 密码输入已中断，未执行任何修改")
        return 1
    if first is None or second is None:
        print("  ❌ 已取消，未执行任何修改")
        return 1
    if first != second:
        print("  ❌ 两次输入的密码不一致，未执行任何修改")
        return 1
    if not MIN_OWNER_PASSWORD_LENGTH <= len(first) <= MAX_OWNER_PASSWORD_LENGTH:
        print(
            f"  ❌ 新密码长度必须为 {MIN_OWNER_PASSWORD_LENGTH}-{MAX_OWNER_PASSWORD_LENGTH} 个字符"
        )
        return 1
    try:
        with owner_recovery_lock(Path(path).resolve().parent):
            account = recover_owner_account(path, username, first)
    except (OwnerServiceError, OSError, RecoveryInProgressError) as error:
        print(f"  ❌ Owner 恢复失败: {error}")
        return 1
    print(f"  ✅ Owner 账户已恢复: {account.username}")
    print("  旧会话已撤销，请使用新登录名和密码进入 Web。")
    return 0


def run_owner_menu() -> int:
    """运行固定三项 Owner 菜单，TTY 下支持方向键。"""
    menu = TerminalMenu(input_fn=input, output_fn=print)
    last_exit_code = 0
    while True:
        try:
            choice = menu.choose(
                "Owner 账户",
                (
                    MenuItem("1", "查看 Owner 账号信息"),
                    MenuItem("2", "恢复 Owner 账号"),
                ),
                breadcrumb="ElfieNest / Owner",
                back_label="返回首页",
            )
        except (EOFError, KeyboardInterrupt):
            return 1
        if choice is None:
            return last_exit_code
        if choice == "1":
            last_exit_code = show_owner_account_page(menu)
        elif choice == "2":
            last_exit_code = recover_owner_interactive(menu=menu)
