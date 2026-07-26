"""Contract tests for the shared Developer Tools Vite build."""

from pathlib import Path

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
