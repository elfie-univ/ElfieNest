from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from infrastructure.models.ollama_platform import (
    OFFICIAL_INSTALL_URLS,
    OllamaBinding,
    OllamaPlatformAdapter,
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


class _Completed:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""
