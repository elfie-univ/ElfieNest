from pathlib import Path

import pytest

from app.interfaces.web.build_discovery import (
    WebBuildManifestMalformedError,
    WebBuildManifestMissingError,
    discover_web_build,
)


def test_discover_web_build_raises_clear_error_when_manifest_is_missing(
    tmp_path: Path,
) -> None:
    # Given: an otherwise valid root build directory without a Vite manifest.
    build_dir = tmp_path / "build" / "web"
    build_dir.mkdir(parents=True)

    # When: Core discovers the Web build output.
    with pytest.raises(
        WebBuildManifestMissingError,
        match=r"cd app/interfaces/web/frontend && pnpm build",
    ):
        discover_web_build(build_dir)

    # Then: the missing generated artifact is not silently accepted.


def test_discover_web_build_raises_clear_error_when_manifest_is_malformed(
    tmp_path: Path,
) -> None:
    # Given: a generated output directory with invalid manifest JSON.
    build_dir = tmp_path / "build" / "web"
    build_dir.mkdir(parents=True)
    (build_dir / "manifest.json").write_text("not-json", encoding="utf-8")

    # When: Core discovers the Web build output.
    with pytest.raises(WebBuildManifestMalformedError, match="malformed"):
        discover_web_build(build_dir)

    # Then: an incomplete artifact cannot be mounted as a Web build.


def test_discover_web_build_accepts_manifest_with_one_react_shell(
    tmp_path: Path,
) -> None:
    # Given: a Vite manifest for the one generated React application shell.
    build_dir = tmp_path / "build" / "web"
    build_dir.mkdir(parents=True)
    manifest = """{
      "index.html": {"file": "assets/app.js"}
    }"""
    (build_dir / "manifest.json").write_text(manifest, encoding="utf-8")

    # When: Core discovers the Web build output.
    web_build = discover_web_build(build_dir)

    # Then: it receives the generated build location and manifest path.
    assert web_build.directory == build_dir
    assert web_build.manifest_path == build_dir / "manifest.json"


def test_web_build_exposes_only_manifest_listed_public_assets(
    tmp_path: Path,
) -> None:
    # Given: the React shell imports its entry plus one shared asset.
    build_dir = tmp_path / "build" / "web"
    assets = build_dir / "assets"
    assets.mkdir(parents=True)
    (build_dir / "index.html").write_text("app", encoding="utf-8")
    (assets / "app.js").write_text("app", encoding="utf-8")
    (assets / "shared.js").write_text("shared", encoding="utf-8")
    (assets / "logo.png").write_bytes(b"logo")
    brands = build_dir / "brands"
    brands.mkdir()
    (brands / "openai.svg").write_text("<svg />", encoding="utf-8")
    (build_dir / "manifest.json").write_text(
        """{
          "index.html": {"file": "assets/app.js", "imports": ["shared"], "assets": ["assets/logo.png", "brands/openai.svg"]},
          "shared": {"file": "assets/shared.js"}
        }""",
        encoding="utf-8",
    )

    # When: Core reads the manifest-derived asset visibility.
    web_build = discover_web_build(build_dir)

    # Then: only manifest-listed shell assets can be read.
    assert web_build.shell_path().read_text() == "app"
    assert web_build.asset_path("assets/app.js").read_text() == "app"
    assert web_build.asset_path("assets/shared.js").read_text() == "shared"
    assert web_build.asset_path("assets/logo.png").read_bytes() == b"logo"
    assert web_build.asset_path("brands/openai.svg").read_text() == "<svg />"
    with pytest.raises(FileNotFoundError):
        web_build.asset_path("assets/unknown.js")
