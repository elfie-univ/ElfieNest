from __future__ import annotations

import signal
import subprocess
from pathlib import Path

import pytest

from infrastructure.models.ollama.ollama_platform import (
    OFFICIAL_INSTALL_URLS,
    OllamaBinding,
    OllamaPlatformAdapter,
    OllamaProcessIdentity,
)


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_adapter_reports_deleted_binding_without_scanning_another_endpoint() -> None:
    adapter = OllamaPlatformAdapter(
        platform_name="linux",
        request_opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")),
    )

    probe = adapter.probe(
        OllamaBinding(
            api_base="http://127.0.0.1:11434",
            platform="linux",
            install_kind="binary",
            launch_target="/missing/ollama",
            version="0.12.0",
        )
    )

    assert probe.state == "deleted"
    assert probe.endpoint == "http://127.0.0.1:11434"


def test_official_installer_is_downloaded_then_runs_only_the_fixed_template() -> None:
    commands: list[tuple[str, ...]] = []
    adapter = OllamaPlatformAdapter(
        platform_name="win32",
        request_opener=lambda *_args, **_kwargs: _Response(b"Write-Output official"),
        command_runner=lambda command, **_kwargs: (
            commands.append(tuple(command)) or _Completed(0)
        ),
    )

    installer = adapter.download_official_installer()
    with pytest.raises(PermissionError, match="用户确认"):
        adapter.run_confirmed_installer(installer, user_confirmed=False)
    assert commands == []

    adapter.run_confirmed_installer(installer, user_confirmed=True)

    assert installer.source_url == OFFICIAL_INSTALL_URLS["win32"]
    assert len(installer.sha256) == 64
    assert commands == [installer.command]


def test_official_binding_with_invalid_platform_signature_requires_repair(
    tmp_path: Path,
) -> None:
    application = tmp_path / "Ollama.app"
    application.mkdir()
    adapter = OllamaPlatformAdapter(
        platform_name="darwin",
        command_runner=lambda *_args, **_kwargs: _Completed(1),
    )
    binding = OllamaBinding(
        api_base="http://127.0.0.1:11434",
        platform="darwin",
        install_kind="official-script",
        launch_target=str(application),
        version="0.12.0",
        installer_source_url=OFFICIAL_INSTALL_URLS["darwin"],
        installer_sha256="a" * 64,
    )

    probe = adapter.probe(binding)

    assert probe.state == "repair_required"
    assert probe.endpoint == binding.api_base


def test_start_bound_installation_launches_without_waiting_for_serve_process(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "ollama"
    executable.write_text("binary", encoding="utf-8")
    launched: list[tuple[tuple[str, ...], dict[str, object]]] = []
    adapter = OllamaPlatformAdapter(
        platform_name="linux",
        process_launcher=lambda command, **kwargs: launched.append(
            (tuple(command), kwargs)
        ),
    )

    adapter.start_bound_installation(
        OllamaBinding(
            api_base="http://127.0.0.1:11434",
            platform="linux",
            install_kind="binary",
            launch_target=str(executable),
            version="0.12.0",
        )
    )

    assert launched == [
        (
            (str(executable), "serve"),
            {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "start_new_session": True,
            },
        )
    ]


def test_darwin_open_helper_returns_the_new_ollama_app_identity(monkeypatch) -> None:
    identity = OllamaProcessIdentity(
        900,
        "/Applications/Ollama.app/Contents/MacOS/Ollama",
        "birth-900",
    )
    ps_outputs = [
        _Completed(0, stdout=""),
        _Completed(
            0,
            stdout="900 /Applications/Ollama.app/Contents/MacOS/Ollama --hidden\n",
        ),
    ]
    launched: list[tuple[tuple[str, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        "infrastructure.models.ollama.ollama_platform.process_identity",
        lambda pid: identity if pid == identity.pid else None,
    )
    adapter = OllamaPlatformAdapter(
        platform_name="darwin",
        command_runner=lambda *_args, **_kwargs: ps_outputs.pop(0),
        process_launcher=lambda command, **kwargs: (
            launched.append((tuple(command), kwargs)) or _Process(123)
        ),
    )

    result = adapter.start_bound_installation(
        OllamaBinding(
            api_base="http://127.0.0.1:11434",
            platform="darwin",
            install_kind="existing-public",
            launch_target="/Applications/Ollama.app",
            version="0.32.11",
        )
    )

    assert result == identity
    assert launched[0][0] == (
        "/usr/bin/open",
        "-a",
        "/Applications/Ollama.app",
    )


def test_darwin_existing_ollama_app_is_not_claimed_as_owned(monkeypatch) -> None:
    identity = OllamaProcessIdentity(
        900,
        "/Applications/Ollama.app/Contents/MacOS/Ollama",
        "birth-900",
    )
    launched: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        "infrastructure.models.ollama.ollama_platform.process_identity",
        lambda pid: identity if pid == identity.pid else None,
    )
    adapter = OllamaPlatformAdapter(
        platform_name="darwin",
        command_runner=lambda *_args, **_kwargs: _Completed(
            0,
            stdout="900 /Applications/Ollama.app/Contents/MacOS/Ollama --hidden\n",
        ),
        process_launcher=lambda command, **_kwargs: (
            launched.append(tuple(command)) or _Process(123)
        ),
    )

    result = adapter.start_bound_installation(
        OllamaBinding(
            api_base="http://127.0.0.1:11434",
            platform="darwin",
            install_kind="official-script",
            launch_target="/Applications/Ollama.app",
            version="0.32.11",
            installer_source_url=OFFICIAL_INSTALL_URLS["darwin"],
            installer_sha256="a" * 64,
        )
    )

    assert result is None
    assert launched == [("/usr/bin/open", "-a", "/Applications/Ollama.app")]


def test_stop_started_process_targets_only_a_matching_process_group_leader(
    monkeypatch,
) -> None:
    identity = OllamaProcessIdentity(900, "/usr/local/bin/ollama", "birth-900")
    current = [identity, None]
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "infrastructure.models.ollama.ollama_platform.process_identity",
        lambda _pid: current.pop(0),
    )
    monkeypatch.setattr(
        "infrastructure.models.ollama.ollama_platform.os.getpgid",
        lambda pid: pid,
    )
    monkeypatch.setattr(
        "infrastructure.models.ollama.ollama_platform.os.killpg",
        lambda pid, sig: signals.append((pid, sig)),
    )

    OllamaPlatformAdapter(platform_name="darwin").stop_started_process(
        identity, timeout_seconds=0.1
    )

    assert signals == [(identity.pid, signal.SIGTERM)]


def test_linux_official_binding_requires_recorded_script_provenance(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "ollama"
    executable.write_text("binary", encoding="utf-8")
    adapter = OllamaPlatformAdapter(
        platform_name="linux",
        request_opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")),
    )
    binding = OllamaBinding(
        api_base="http://127.0.0.1:11434",
        platform="linux",
        install_kind="official-script",
        launch_target=str(executable),
        version="0.12.0",
    )

    probe = adapter.probe(binding)

    assert probe.state == "repair_required"


class _Process:
    def __init__(self, pid: int) -> None:
        self.pid = pid


class _Completed:
    def __init__(self, returncode: int, *, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
