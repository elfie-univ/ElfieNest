"""公共 Ollama 的平台探测、官方安装脚本与固定绑定适配器。"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ContextManager, Final, Literal, Protocol, Tuple
from urllib.parse import urlsplit

from infrastructure.models.ollama.ollama_platform_commands import (
    PlatformName,
    current_platform,
    launch_command,
    official_command,
    official_launch_target,
)

OllamaState = Literal[
    "absent",
    "healthy",
    "stopped",
    "deleted",
    "installing",
    "failed",
    "cancelled",
    "repair_required",
]
DEFAULT_OLLAMA_ENDPOINT: Final[str] = "http://127.0.0.1:11434"
OFFICIAL_INSTALL_URLS: Final[dict[PlatformName, str]] = {
    "darwin": "https://ollama.com/install.sh",
    "linux": "https://ollama.com/install.sh",
    "win32": "https://ollama.com/install.ps1",
}


def is_safe_local_endpoint(endpoint: str) -> bool:
    """Accept only explicit loopback HTTP endpoints for the local service."""
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}
        and port is not None
        and 0 < port <= 65535
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


@dataclass(frozen=True)
class OllamaBinding:
    api_base: str
    platform: PlatformName
    install_kind: str
    launch_target: str
    version: str
    installer_source_url: str = ""
    installer_sha256: str = ""


@dataclass(frozen=True)
class OllamaProbe:
    state: OllamaState
    endpoint: str
    version: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class OllamaProcessIdentity:
    """Exact identity evidence for an Ollama process started by ElfieNest."""

    pid: int
    executable: str
    birth_identity: str


@dataclass(frozen=True)
class DownloadedInstaller:
    source_url: str
    sha256: str
    script_path: Path
    command: Tuple[str, ...]


class _ReadableResponse(Protocol):
    def read(self) -> bytes: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep a local Ollama request from being redirected to another host."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


class OllamaPlatformAdapter:
    """Only interacts with an explicit binding; it never scans for a replacement."""

    def __init__(
        self,
        *,
        platform_name: PlatformName | None = None,
        request_opener: Callable[
            ..., ContextManager[_ReadableResponse]
        ] = _NO_REDIRECT_OPENER.open,
        command_runner: Callable[
            ..., subprocess.CompletedProcess[str]
        ] = subprocess.run,
        process_launcher: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self.platform = platform_name or current_platform()
        self._request_opener = request_opener
        self._command_runner = command_runner
        self._process_launcher = process_launcher

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        if binding is None:
            return OllamaProbe("absent", "")
        if not is_safe_local_endpoint(binding.api_base):
            return OllamaProbe(
                "repair_required", "", detail="Ollama endpoint 必须是本机回环地址"
            )
        if binding.install_kind == "official-script":
            try:
                self.verify_recorded_installation(binding)
            except RuntimeError as exc:
                return OllamaProbe("repair_required", binding.api_base, detail=str(exc))
        try:
            with self._request_opener(
                urllib.request.Request(f"{binding.api_base.rstrip('/')}/api/version"),
                timeout=2.0,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            version = str(payload.get("version", ""))
            if version:
                return OllamaProbe("healthy", binding.api_base, version=version)
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            pass
        if binding.launch_target and Path(binding.launch_target).exists():
            return OllamaProbe("stopped", binding.api_base)
        return OllamaProbe(
            "deleted", binding.api_base, detail="已绑定的 Ollama 安装不存在"
        )

    def download_official_installer(self) -> DownloadedInstaller:
        source_url = OFFICIAL_INSTALL_URLS[self.platform]
        suffix = ".ps1" if self.platform == "win32" else ".sh"
        with self._request_opener(source_url, timeout=30.0) as response:
            payload = response.read()
        if not payload:
            raise RuntimeError("官方 Ollama 安装脚本为空")
        directory = Path(tempfile.mkdtemp(prefix="elfienest-ollama-"))
        script_path = directory / f"official-install{suffix}"
        script_path.write_bytes(payload)
        return DownloadedInstaller(
            source_url=source_url,
            sha256=hashlib.sha256(payload).hexdigest(),
            script_path=script_path,
            command=official_command(self.platform, script_path),
        )

    def list_models(self, binding: OllamaBinding) -> Tuple[str, ...]:
        """Read tags from exactly the saved endpoint; never discover another host."""
        if not is_safe_local_endpoint(binding.api_base):
            raise ValueError("Ollama endpoint 必须是本机回环地址")
        try:
            with self._request_opener(
                urllib.request.Request(f"{binding.api_base.rstrip('/')}/api/tags"),
                timeout=5.0,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError("Ollama 模型清单健康检查失败") from exc
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise RuntimeError("Ollama 模型清单格式无效")
        models: list[str] = []
        for item in raw_models:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                models.append(item["name"])
        return tuple(models)

    def pull_model(self, binding: OllamaBinding, model_id: str) -> None:
        """Pull one model through the fixed Ollama endpoint, never through a shell."""
        if not is_safe_local_endpoint(binding.api_base):
            raise ValueError("Ollama endpoint 必须是本机回环地址")
        body = json.dumps({"name": model_id, "stream": False}).encode("utf-8")
        request = urllib.request.Request(
            f"{binding.api_base.rstrip('/')}/api/pull",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._request_opener(request, timeout=3600.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError("Ollama 模型拉取失败") from exc
        if str(payload.get("status", "")) not in {"success", ""}:
            raise RuntimeError("Ollama 未确认模型拉取完成")

    def run_confirmed_installer(
        self,
        installer: DownloadedInstaller,
        *,
        user_confirmed: bool,
    ) -> None:
        """Run only a locally downloaded script from the fixed official domain."""
        if not user_confirmed:
            raise PermissionError("必须由用户确认后才能安装公共 Ollama")
        if installer.source_url != OFFICIAL_INSTALL_URLS[self.platform]:
            raise ValueError("拒绝执行非官方 Ollama 安装来源")
        if not installer.script_path.is_file():
            raise FileNotFoundError("官方 Ollama 安装脚本已丢失")
        actual_sha256 = hashlib.sha256(installer.script_path.read_bytes()).hexdigest()
        if actual_sha256 != installer.sha256:
            raise RuntimeError("官方 Ollama 安装脚本校验失败")
        result = self._command_runner(
            installer.command,
            check=False,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError("官方 Ollama 安装失败；请查看本机安装日志")

    def verify_recorded_installation(self, binding: OllamaBinding) -> None:
        """Verify only a recorded official installation before starting or saving it."""
        if binding.install_kind != "official-script":
            return
        if binding.platform != self.platform:
            raise RuntimeError("Ollama 绑定的平台与当前系统不一致")
        if (
            binding.installer_source_url != OFFICIAL_INSTALL_URLS[binding.platform]
            or len(binding.installer_sha256) != 64
        ):
            raise RuntimeError("官方 Ollama 安装来源记录不完整")
        if not binding.launch_target or not Path(binding.launch_target).exists():
            raise RuntimeError("已记录的官方 Ollama 安装文件不存在")
        if binding.platform == "darwin":
            self._require_success(
                (
                    "/usr/bin/codesign",
                    "--verify",
                    "--deep",
                    "--strict",
                    binding.launch_target,
                ),
                "Ollama macOS 签名校验失败",
            )
        elif binding.platform == "win32":
            self._require_success(
                (
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "if ((Get-AuthenticodeSignature -FilePath $args[0]).Status -ne 'Valid') { exit 1 }",
                    binding.launch_target,
                ),
                "Ollama Windows 签名校验失败",
            )

    def _require_success(self, command: Tuple[str, ...], failure: str) -> None:
        result = self._command_runner(
            command, check=False, text=True, capture_output=True
        )
        if result.returncode != 0:
            raise RuntimeError(failure)

    def start_bound_installation(
        self, binding: OllamaBinding
    ) -> OllamaProcessIdentity | None:
        """Start exactly the recorded public installation without blocking the caller."""
        self.verify_recorded_installation(binding)
        command = launch_command(
            binding.platform,
            binding.install_kind,
            binding.launch_target,
        )
        process = self._process_launcher(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid = getattr(process, "pid", None)
        if not isinstance(pid, int) or pid <= 0:
            return None
        for _ in range(20):
            identity = process_identity(pid)
            if identity is not None:
                return identity
            time.sleep(0.05)
        return None

    def stop_started_process(
        self,
        identity: OllamaProcessIdentity,
        *,
        force: bool = False,
        timeout_seconds: float = 5.0,
    ) -> None:
        """Stop only an exact process identity previously returned by this adapter."""
        current = process_identity(identity.pid)
        if current is None or current != identity:
            raise RuntimeError("拒绝停止身份已变化的 Ollama 进程")
        if os.name == "nt":
            os.kill(identity.pid, signal.SIGTERM)
        else:
            try:
                os.killpg(identity.pid, signal.SIGKILL if force else signal.SIGTERM)
            except ProcessLookupError:
                return
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while process_identity(identity.pid) is not None:
            if time.monotonic() >= deadline:
                if not force:
                    self.stop_started_process(
                        identity,
                        force=True,
                        timeout_seconds=1.0,
                    )
                    return
                raise TimeoutError("Ollama 进程未在期限内退出")
            time.sleep(0.1)

    def official_binding_after_install(
        self,
        *,
        endpoint: str,
        installer: DownloadedInstaller,
    ) -> OllamaBinding:
        """Resolve only documented official paths after a confirmed first install."""
        if not is_safe_local_endpoint(endpoint):
            raise ValueError("Ollama endpoint 必须是本机回环地址")
        target, install_kind = official_launch_target(self.platform)
        binding = OllamaBinding(
            api_base=endpoint,
            platform=self.platform,
            install_kind=install_kind,
            launch_target=target,
            version="",
            installer_source_url=installer.source_url,
            installer_sha256=installer.sha256,
        )
        self.verify_recorded_installation(binding)
        return binding


def wait_for_healthy(
    adapter: OllamaPlatformAdapter,
    binding: OllamaBinding,
    *,
    timeout_seconds: float = 10.0,
) -> OllamaProbe:
    """Poll briefly after launching Ollama so startup is not reported too early."""
    deadline = time.monotonic() + timeout_seconds
    probe = adapter.probe(binding)
    while probe.state != "healthy" and time.monotonic() < deadline:
        time.sleep(0.25)
        probe = adapter.probe(binding)
    return probe


def process_birth_identity(pid: int) -> str:
    """Return a platform process-start identity, or an empty value if unavailable."""
    proc_stat = Path("/proc") / str(pid) / "stat"
    try:
        if proc_stat.is_file():
            raw = proc_stat.read_text(encoding="utf-8")
            remainder = raw.rpartition(")")[2].split()
            if len(remainder) > 19:
                return remainder[19]
    except OSError:
        pass
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip()


def process_executable(pid: int) -> str:
    """Return the current executable path when the platform exposes it."""
    try:
        return str(Path(os.readlink(f"/proc/{pid}/exe")).resolve())
    except (FileNotFoundError, OSError, RuntimeError):
        try:
            completed = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return completed.stdout.strip()


def process_identity(pid: int) -> OllamaProcessIdentity | None:
    """Read exact process evidence without granting control from PID alone."""
    birth = process_birth_identity(pid)
    executable = process_executable(pid)
    if not birth or not executable:
        return None
    return OllamaProcessIdentity(pid, executable, birth)
