from __future__ import annotations

import signal
import subprocess
from pathlib import Path

import pytest

from app.orchestration.lifecycle.ports import ProcessIdentityEvidence
from infrastructure.models.ollama.ollama_platform import (
    OFFICIAL_INSTALL_URLS,
    OllamaBinding,
    OllamaPlatformAdapter,
    OllamaProcessIdentity,
)


class _MissingIdentityReader:
    def read(self, _pid: int) -> ProcessIdentityEvidence | None:
        return None


class _SequenceIdentityReader:
    def __init__(self, evidence: list[ProcessIdentityEvidence | None]) -> None:
        self._evidence = evidence

    def read(self, _pid: int) -> ProcessIdentityEvidence | None:
        return self._evidence.pop(0)


def _evidence(identity: OllamaProcessIdentity) -> ProcessIdentityEvidence:
    return ProcessIdentityEvidence(
        identity.pid,
        identity.executable,
        identity.birth_identity,
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
        process_identity_reader=_MissingIdentityReader(),
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
        process_identity_reader=_MissingIdentityReader(),
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
        process_identity_reader=_MissingIdentityReader(),
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
        process_identity_reader=_MissingIdentityReader(),
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


def test_windows_started_ollama_uses_injected_exact_process_identity(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "ollama.exe"
    executable.write_text("binary", encoding="utf-8")
    evidence = ProcessIdentityEvidence(
        pid=900,
        executable=str(executable),
        birth_identity="win32-create:900",
    )

    class Reader:
        def read(self, pid: int) -> ProcessIdentityEvidence | None:
            return evidence if pid == evidence.pid else None

    adapter = OllamaPlatformAdapter(
        platform_name="win32",
        process_identity_reader=Reader(),
        process_launcher=lambda *_args, **_kwargs: _Process(evidence.pid),
    )

    identity = adapter.start_bound_installation(
        OllamaBinding(
            api_base="http://127.0.0.1:11434",
            platform="win32",
            install_kind="binary",
            launch_target=str(executable),
            version="0.12.0",
        )
    )

    assert identity == OllamaProcessIdentity(
        evidence.pid,
        evidence.executable,
        evidence.birth_identity,
    )


def test_darwin_open_helper_returns_the_new_ollama_app_identity() -> None:
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
    adapter = OllamaPlatformAdapter(
        process_identity_reader=_SequenceIdentityReader([_evidence(identity)]),
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


def test_darwin_existing_ollama_app_is_not_claimed_as_owned(tmp_path: Path) -> None:
    application = tmp_path / "Ollama.app"
    application.mkdir()
    executable = application / "Contents" / "MacOS" / "Ollama"
    identity = OllamaProcessIdentity(
        900,
        str(executable),
        "birth-900",
    )
    launched: list[tuple[str, ...]] = []
    adapter = OllamaPlatformAdapter(
        process_identity_reader=_SequenceIdentityReader([_evidence(identity)]),
        platform_name="darwin",
        command_runner=lambda *_args, **_kwargs: _Completed(
            0,
            stdout=f"900 {executable} --hidden\n",
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
            launch_target=str(application),
            version="0.32.11",
            installer_source_url=OFFICIAL_INSTALL_URLS["darwin"],
            installer_sha256="a" * 64,
        )
    )

    assert result is None
    assert launched == [("/usr/bin/open", "-a", str(application))]


def test_stop_started_process_targets_only_a_matching_process_group_leader(
    monkeypatch,
) -> None:
    identity = OllamaProcessIdentity(900, "/usr/local/bin/ollama", "birth-900")
    current = [identity, None]
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "infrastructure.models.ollama.ollama_platform.os.getpgid",
        lambda pid: pid,
    )
    monkeypatch.setattr(
        "infrastructure.models.ollama.ollama_platform.os.killpg",
        lambda pid, sig: signals.append((pid, sig)),
    )

    OllamaPlatformAdapter(
        platform_name="darwin",
        process_identity_reader=_SequenceIdentityReader(
            [None if item is None else _evidence(item) for item in current]
        ),
    ).stop_started_process(identity, timeout_seconds=0.1)

    assert signals == [(identity.pid, signal.SIGTERM)]


def test_linux_official_binding_requires_recorded_script_provenance(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "ollama"
    executable.write_text("binary", encoding="utf-8")
    adapter = OllamaPlatformAdapter(
        process_identity_reader=_MissingIdentityReader(),
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
