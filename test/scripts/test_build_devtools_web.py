"""Contract tests for the shared Developer Tools Vite build."""

from pathlib import Path

from scripts import build_devtools_web
from scripts.build_devtools_web import bundle_is_current, source_digest


def test_bundle_is_current_only_when_frontend_source_matches(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "frontend"
    source.mkdir()
    (source / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    (output / "index.html").write_text("<main />", encoding="utf-8")
    (output / "build-manifest.json").write_text(
        f'{{"source_digest": "{source_digest(source)}"}}',
        encoding="utf-8",
    )

    # When / Then
    assert bundle_is_current(output, source)

    # When
    (source / "package.json").write_text('{"name":"changed"}', encoding="utf-8")

    # Then
    assert not bundle_is_current(output, source)


def test_ensure_bundle_repairs_an_incomplete_node_modules_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "frontend"
    source.mkdir()
    (source / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    (source / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (source / "node_modules").mkdir()
    output = tmp_path / "output"
    monkeypatch.setattr(build_devtools_web, "WEB_SOURCE", source)
    monkeypatch.setattr(build_devtools_web, "OUTPUT_DIRECTORY", output)
    calls: list[tuple[str, ...]] = []

    def fake_run(command, *, cwd, check):
        calls.append(tuple(command))
        if command[1] == "install":
            binary = cwd / "node_modules" / ".bin" / "tsc"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("", encoding="utf-8")

    monkeypatch.setattr(build_devtools_web.subprocess, "run", fake_run)

    result = build_devtools_web.ensure_bundle(pnpm_command="pnpm")

    assert result == output
    assert calls == [("pnpm", "install", "--frozen-lockfile"), ("pnpm", "run", "build")]
