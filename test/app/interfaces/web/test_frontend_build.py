from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.interfaces.web import frontend_build


def _write_bundle(output: Path, source_digest: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text("<main />", encoding="utf-8")
    (output / "assets").mkdir(exist_ok=True)
    (output / "assets/app.js").write_text("console.log('ok')", encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps({"index.html": {"file": "assets/app.js"}}),
        encoding="utf-8",
    )
    (output / frontend_build.BUILD_MANIFEST_NAME).write_text(
        json.dumps({"source_digest": source_digest}),
        encoding="utf-8",
    )


def test_bundle_is_current_only_when_source_and_generated_shell_match(
    tmp_path: Path,
) -> None:
    source = tmp_path / "frontend"
    source.mkdir()
    (source / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    output = tmp_path / "build" / "web"
    _write_bundle(output, frontend_build.source_digest(source))

    assert frontend_build.bundle_is_current(output, source)

    (source / "package.json").write_text('{"name":"changed"}', encoding="utf-8")

    assert not frontend_build.bundle_is_current(output, source)

    (source / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    (output / "index.html").unlink()

    assert not frontend_build.bundle_is_current(output, source)


def test_ensure_rebuilds_stale_frontend_and_records_post_build_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "frontend"
    source.mkdir()
    (source / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    output = tmp_path / "build" / "web"
    monkeypatch.setattr(frontend_build, "FRONTEND_SOURCE_DIRECTORY", source)
    monkeypatch.setattr(frontend_build, "WEB_BUILD_DIRECTORY", output)
    calls: list[tuple[str, ...]] = []

    def run_pnpm(_frontend_root: Path, arguments: tuple[str, ...]) -> None:
        calls.append(arguments)
        if arguments == ("build",):
            _write_bundle(output, frontend_build.source_digest(source))

    monkeypatch.setattr(frontend_build, "_run_pnpm", run_pnpm)

    frontend_build.ensure_frontend_build(runtime_mode="development")
    frontend_build.ensure_frontend_build(runtime_mode="development")

    assert calls == [("install", "--frozen-lockfile"), ("build",)]
    assert frontend_build.bundle_is_current(output, source)


def test_ensure_does_not_touch_release_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        frontend_build,
        "_run_pnpm",
        lambda *_args: pytest.fail("release mode must not build frontend"),
    )

    frontend_build.ensure_frontend_build(
        runtime_mode="release",
        source=tmp_path / "missing-source",
        output=tmp_path / "missing-output",
    )


def test_run_pnpm_always_uses_repository_pinned_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[tuple[tuple[str, ...], Path, bool]] = []
    monkeypatch.setattr(frontend_build.shutil, "which", lambda _name: "/bin/npx")

    def run(command: tuple[str, ...], *, cwd: Path, check: bool) -> None:
        commands.append((command, cwd, check))

    monkeypatch.setattr(frontend_build.subprocess, "run", run)

    frontend_build._run_pnpm(tmp_path, ("build",))

    assert commands == [
        (
            ("/bin/npx", "--yes", "pnpm@10.12.1", "build"),
            tmp_path,
            True,
        )
    ]


def test_run_pnpm_hides_child_output_for_interactive_launches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("ELFIENEST_INTERACTIVE", "1")
    monkeypatch.setattr(frontend_build.shutil, "which", lambda _name: "/bin/npx")

    def run(command, *, cwd, check, capture_output, text) -> None:
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "check": check,
                "capture_output": capture_output,
                "text": text,
            }
        )

    monkeypatch.setattr(frontend_build.subprocess, "run", run)

    frontend_build._run_pnpm(tmp_path, ("build",))

    assert calls == [
        {
            "command": ("/bin/npx", "--yes", "pnpm@10.12.1", "build"),
            "cwd": tmp_path,
            "check": True,
            "capture_output": True,
            "text": True,
        }
    ]


def test_run_pnpm_keeps_interactive_failure_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ELFIENEST_INTERACTIVE", "1")
    monkeypatch.setattr(frontend_build.shutil, "which", lambda _name: "/bin/npx")

    def run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=("/bin/npx", "--yes", "pnpm@10.12.1", "build"),
            output="vite summary",
            stderr="error: build failed",
        )

    monkeypatch.setattr(frontend_build.subprocess, "run", run)

    with pytest.raises(
        frontend_build.FrontendBuildError, match="error: build failed"
    ) as raised:
        frontend_build._run_pnpm(tmp_path, ("build",))

    assert "vite summary" in str(raised.value)


def test_build_failure_is_typed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "frontend"
    source.mkdir()
    (source / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    monkeypatch.setattr(frontend_build, "_run_pnpm", _raise_build_failure)

    with pytest.raises(frontend_build.FrontendBuildError, match="pnpm failed"):
        frontend_build.ensure_frontend_build(
            runtime_mode="development",
            source=source,
            output=tmp_path / "build" / "web",
        )


def test_ensure_fails_if_source_changes_during_build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "frontend"
    source.mkdir()
    package_json = source / "package.json"
    package_json.write_text('{"name":"before"}', encoding="utf-8")
    output = tmp_path / "build" / "web"

    def run_pnpm(_frontend_root: Path, arguments: tuple[str, ...]) -> None:
        if arguments == ("build",):
            package_json.write_text('{"name":"after"}', encoding="utf-8")
            _write_bundle(output, frontend_build.source_digest(source))

    monkeypatch.setattr(frontend_build, "_run_pnpm", run_pnpm)

    with pytest.raises(frontend_build.FrontendBuildError, match="changed during build"):
        frontend_build.ensure_frontend_build(
            runtime_mode="development", source=source, output=output
        )


def test_ensure_fails_closed_when_build_marker_cannot_be_verified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "frontend"
    source.mkdir()
    (source / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    output = tmp_path / "build" / "web"

    def run_pnpm(_frontend_root: Path, arguments: tuple[str, ...]) -> None:
        if arguments == ("build",):
            _write_bundle(output, frontend_build.source_digest(source))
            (output / frontend_build.BUILD_MANIFEST_NAME).unlink()

    monkeypatch.setattr(frontend_build, "_run_pnpm", run_pnpm)
    monkeypatch.setattr(frontend_build, "_write_build_marker", lambda *_args: None)

    with pytest.raises(
        frontend_build.FrontendBuildError, match="could not be verified"
    ):
        frontend_build.ensure_frontend_build(
            runtime_mode="development", source=source, output=output
        )


def _raise_build_failure(_frontend_root: Path, _arguments: tuple[str, ...]) -> None:
    raise frontend_build.FrontendBuildError("pnpm failed")
