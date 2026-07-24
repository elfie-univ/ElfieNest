"""用户可见的服务生命周期命令。"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional, Sequence

from ai_runtime.storage.data_home import get_elfie_home
from app.features.administration.system_service import (
    default_port_statuses,
    service_port_statuses,
)
from app.orchestration.lifecycle import desktop as desktop_lifecycle
from app.orchestration.lifecycle.helpers import existing_service_command
from app.orchestration.lifecycle.process import (
    DefaultProcessInspector,
    http_port_from_command,
    service_ports_from_command,
    validate_service_ports,
)
from app.orchestration.lifecycle.service import start_service, stop_service
from app.orchestration.lifecycle.types import (
    LaunchFailedError,
    ServiceLifecycleResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_URL = "http://127.0.0.1:8000/"
WEB_HEALTH_URL = "http://127.0.0.1:8000/api/health"


def default_service_command(extra_args: Sequence[str] = ()) -> tuple[str, ...]:
    """Build the background command without the foreground-only force flag."""
    filtered = tuple(argument for argument in extra_args if argument != "--force")
    return (
        sys.executable,
        str((PROJECT_ROOT / "scripts" / "serve.py").resolve()),
        *filtered,
    )


def start_background_service(
    command: Optional[Sequence[str]] = None,
) -> ServiceLifecycleResult:
    """Start the service once; a verified running process is left untouched."""
    launch_command = (
        tuple(command)
        if command is not None
        else default_service_command(("--lan",))
    )
    try:
        http_port = _validated_http_port(launch_command)
    except ValueError as error:
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"服务端口参数无效: {error}")
        )
        _print_start_result(result)
        return result
    result = start_service(
        get_elfie_home(),
        PROJECT_ROOT,
        command=launch_command,
        health_checker=lambda: _web_is_healthy(http_port),
    )
    _print_start_result(result)
    return result


def stop_background_service() -> ServiceLifecycleResult:
    """Stop only the current project's verified service process."""
    result = stop_service(get_elfie_home(), PROJECT_ROOT)
    if result.status == "stopped":
        print("  ✅ 服务已停止")
    elif result.status == "already_stopped":
        print("  ⭕ 服务未运行")
    else:
        print(f"  ❌ 服务停止失败: {result.error}")
    return result


def restart_background_service() -> ServiceLifecycleResult:
    """Stop the current process and start it again with its existing arguments."""
    stopped = stop_service(get_elfie_home(), PROJECT_ROOT)
    if stopped.status == "failed":
        print(f"  ❌ 无法重启服务: {stopped.error}")
        return stopped
    command = stopped.command or default_service_command(("--lan",))
    try:
        http_port = _validated_http_port(command)
    except ValueError as error:
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"服务端口参数无效: {error}")
        )
        print(f"  ❌ 服务重启失败: {result.error}")
        return result
    result = start_service(
        get_elfie_home(),
        PROJECT_ROOT,
        command=tuple(argument for argument in command if argument != "--force"),
        health_checker=lambda: _web_is_healthy(http_port),
    )
    if result.status in {"started", "already_running"}:
        print("  ✅ 服务已重启")
    else:
        print(f"  ❌ 服务重启失败: {result.error}")
    return result


def show_service_status() -> None:
    """Print lifecycle state without duplicating usage/session statistics."""
    print("  📊 服务状态")
    print("  " + "=" * 45)
    print()
    running = existing_service_command(
        get_elfie_home(), PROJECT_ROOT, DefaultProcessInspector()
    )
    if running is None:
        port_statuses = default_port_statuses()
    else:
        _, command = running
        ports = service_ports_from_command(command)
        port_statuses = service_port_statuses(ports[0], ports[2], ports[1])
    for port_status in port_statuses:
        state = "运行中" if port_status.running else "未运行"
        icon = "✅" if port_status.running else "⭕"
        print(f"  {icon} {port_status.name}: {state} (端口 {port_status.port})")
    print()


def open_web_console() -> ServiceLifecycleResult:
    """Ensure a healthy service and open the Web management console."""
    running = existing_service_command(
        get_elfie_home(), PROJECT_ROOT, DefaultProcessInspector()
    )
    if running is not None:
        _, running_command = running
        port = http_port_from_command(running_command)
        if not _web_is_healthy(port):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"已登记服务但 Web 端口 {port} 未通过健康检查"),
            )
            print(f"  ❌ 无法打开 Web 管理台: {result.error}")
            return result
    else:
        result = start_background_service()
        if result.status not in {"started", "already_running"}:
            return result
        port = http_port_from_command(
            result.command or default_service_command(("--lan",))
        )
        if not _web_is_healthy(port):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"服务已启动但 Web 端口 {port} 未通过健康检查"),
            )
            print(f"  ❌ 无法打开 Web 管理台: {result.error}")
            return result
    web_url = f"http://127.0.0.1:{port}/"
    webbrowser.open(web_url)
    print(f"  🌐 已打开 Web 管理台: {web_url}")
    return ServiceLifecycleResult(status="already_running")


def start_desktop_application() -> ServiceLifecycleResult:
    """Explicitly start the packaged Electron Desktop supervisor."""
    result = desktop_lifecycle.start_desktop_application(
        get_elfie_home(), PROJECT_ROOT, health_checker=_web_is_healthy
    )
    if result.status in {"started", "already_running"}:
        print(f"  ✅ Desktop 已启动 (PID {result.pid})")
    else:
        print(f"  ❌ Desktop 启动失败: {result.error}")
    return result


def _web_is_healthy(port: int = 8000) -> bool:
    health_url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(health_url, timeout=0.5) as response:
            return response.status == 200
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


def _validated_http_port(command: Sequence[str]) -> int:
    """Parse and validate HTTP/WS ports before spawning a service process."""
    ports = service_ports_from_command(command)
    error = validate_service_ports(ports[0], ports[2], ports[1])
    if error:
        raise ValueError(error)
    return ports[0]


def _print_start_result(result: ServiceLifecycleResult) -> None:
    if result.status == "started":
        print(f"  ✅ 服务已启动 (PID {result.pid})")
    elif result.status == "already_running":
        print(f"  ⭕ 服务已在运行 (PID {result.pid})")
    else:
        print(f"  ❌ 服务启动失败: {result.error}")
