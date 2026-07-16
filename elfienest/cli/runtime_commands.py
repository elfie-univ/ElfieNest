from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from elfienest.operations.service import (
    DatabaseUnavailableError,
    backup_database,
    collect_usage_stats,
    default_port_statuses,
    list_active_sessions,
    list_table_counts,
    reset_database,
)

VERSION = "1.0.0"
WEB_URL = "http://127.0.0.1:8000/"
WEB_HEALTH_URL = "http://127.0.0.1:8000/api/health"
WEB_START_TIMEOUT_SECONDS = 10.0
WEB_STOP_TIMEOUT_SECONDS = 5.0
WEB_LOG_PATH = Path("/tmp/elfienest-web.log")


def _start_web_service_process() -> subprocess.Popen[str]:
    WEB_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    popen_options = {
        "stdin": subprocess.DEVNULL,
        "stdout": None,
        "stderr": subprocess.STDOUT,
        "text": True,
    }
    if os.name == "nt":
        popen_options["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        popen_options["start_new_session"] = True
    with WEB_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write("\n=== ElfieNest web service start ===\n")
        popen_options["stdout"] = log_file
        return subprocess.Popen(
            [sys.executable, "scripts/serve.py", "--fallback", "--force"],
            **popen_options,
        )


def _wait_for_web_ready(process: subprocess.Popen[str]) -> bool:
    deadline = time.monotonic() + WEB_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(WEB_HEALTH_URL, timeout=0.5) as response:
                if response.status == 200:
                    return True
        except (OSError, TimeoutError, urllib.error.URLError):
            time.sleep(0.5)

    return False


def _wait_for_web_stopped() -> bool:
    deadline = time.monotonic() + WEB_STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(WEB_HEALTH_URL, timeout=0.3).close()
        except (OSError, TimeoutError, urllib.error.URLError):
            return True
        time.sleep(0.1)
    return False


def _terminate_if_running(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        process.kill()


def _print_recent_web_log() -> None:
    if not WEB_LOG_PATH.exists():
        return
    try:
        lines = WEB_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    recent_lines = lines[-8:]
    if not recent_lines:
        return
    print("  【最近启动日志】")
    for line in recent_lines:
        print(f"    {line}")


def _print_web_start_failure(process: subprocess.Popen[str]) -> None:
    returncode = process.poll()
    if returncode is None:
        print("  ❌ 服务启动超时")
    else:
        print(f"  ❌ 服务启动失败 (退出码 {returncode})")
    print(f"  📝 启动日志: {WEB_LOG_PATH}")
    _print_recent_web_log()
    print("  💡 请运行 ./elfienest.sh serve --force 查看完整错误")
    print()


def show_status() -> None:
    print("  📊 服务状态")
    print("  " + "=" * 45)
    print()

    for port_status in default_port_statuses():
        if port_status.running:
            print(f"  ✅ {port_status.name}: 运行中 (端口 {port_status.port})")
        else:
            print(f"  ⭕ {port_status.name}: 未运行 (端口 {port_status.port})")

    print()
    try:
        stats = collect_usage_stats()
        print(f"  📦 数据库: {stats.user_count} 用户, {stats.elfie_count} 精灵")
    except DatabaseUnavailableError:
        print("  ❌ 数据库未初始化")

    print()


def start_web() -> None:
    print("  🌐 启动服务并打开浏览器...")
    print()

    process = _start_web_service_process()
    if not _wait_for_web_ready(process):
        _print_web_start_failure(process)
        _terminate_if_running(process)
        return

    print(f"  打开浏览器: {WEB_URL}")
    webbrowser.open(WEB_URL)

    print("  ✅ 服务已启动")
    print()


def show_stats() -> None:
    print("  📈 使用统计")
    print("  " + "=" * 45)
    print()

    try:
        stats = collect_usage_stats()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 无法读取统计: {e}")
        print()
        return

    print("  【用户统计】")
    print(f"    总用户数: {stats.user_count}")
    print(f"    Owner 数: {stats.owner_count}")
    print(f"    普通用户: {stats.user_count - stats.owner_count}")
    print()

    print("  【精灵统计】")
    print(f"    总精灵数: {stats.elfie_count}")
    for row in stats.anatomy_stats:
        print(f"    {row.anatomy_type}: {row.count}")
    print()

    print("  【会话统计】")
    print(f"    活跃会话: {stats.session_count}")
    print()


def show_sessions() -> None:
    print("  👥 会话管理")
    print("  " + "=" * 45)
    print()

    try:
        sessions = list_active_sessions()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 无法读取会话: {e}")
        print()
        return

    if sessions:
        print("  【在线用户】")
        for session in sessions:
            token_short = session.token[:8] + "..."
            print(
                f"    • {session.username} "
                f"(token: {token_short}, 过期: {session.expires_at})"
            )
    else:
        print("  暂无活跃会话")

    print()


def show_logs() -> None:
    print("  📝 日志查看")
    print("  " + "=" * 45)
    print()

    log_files = [
        "/tmp/serve.log",
        "/tmp/serve_full.log",
        "/tmp/final_serve.log",
    ]

    for log_file in log_files:
        if os.path.exists(log_file):
            print(f"  【{log_file}】")
            try:
                with open(log_file) as file:
                    lines = file.readlines()[-20:]
            except OSError:
                print("    无法读取")
            else:
                for line in lines:
                    print(f"    {line.rstrip()}")
            print()

    print("  💡 查看完整日志: tail -100 /tmp/serve.log")
    print()


def dispatch_db(subcmd: str | None) -> None:
    print("  🗄️  数据库工具")
    print("  " + "=" * 45)
    print()

    if subcmd == "backup":
        backup_db()
    elif subcmd == "reset":
        reset_db()
    else:
        show_db()

    print()


def backup_db() -> None:
    try:
        backup_path = backup_database()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 备份失败: {e}")
        return
    print(f"  ✅ 数据库已备份到: {backup_path}")


def reset_db() -> None:
    print("  ⚠️  这将删除所有数据，是否继续？")
    choice = input("输入 'yes' 确认: ").strip()
    if choice.lower() != "yes":
        return
    try:
        reset_database()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 删除失败: {e}")
        return
    print("  ✅ 数据库已删除，重启服务将自动创建新数据库")


def show_db() -> None:
    print("  可用命令:")
    print("    elfienest db backup  - 备份数据库")
    print("    elfienest db reset   - 重置数据库")
    print()

    try:
        table_counts = list_table_counts()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 无法读取数据库: {e}")
        return

    print("  【数据库表】")
    for table_count in table_counts:
        print(f"    • {table_count.name}: {table_count.count} 条记录")


def show_version() -> None:
    print(f"  ElfieNest v{VERSION}")
    print()
    print("  🦊 仿生生命体系统")
    print("  一个基于三层大脑架构的 AI 生物模拟系统")
    print()


def restart_service() -> None:
    print("  🔄 重启服务...")

    try:
        subprocess.run(["pkill", "-f", "serve.py"], capture_output=True)
        print("  ✓ 已停止旧服务")
    except OSError:
        pass

    if not _wait_for_web_stopped():
        print("  ❌ 旧服务未能在 5 秒内停止，已取消重启")
        return

    print("  ✓ 启动新服务...")
    process = _start_web_service_process()

    if not _wait_for_web_ready(process):
        _print_web_start_failure(process)
        _terminate_if_running(process)
        return

    print("  ✅ 服务已重启")


def stop_service() -> None:
    print("  🛑 停止服务...")
    try:
        subprocess.run(["pkill", "-f", "serve.py"], check=True)
        print("  ✅ 服务已停止")
    except (OSError, subprocess.CalledProcessError):
        print("  ⚠️  服务未运行")
