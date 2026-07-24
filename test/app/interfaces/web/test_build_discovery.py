from pathlib import Path

import pytest

from app.interfaces.web.build_discovery import WebBuildManifestMissingError
from app.interfaces.web.build_discovery import WebBuildManifestMalformedError
from app.interfaces.web.build_discovery import discover_web_build


def test_discover_web_build_raises_clear_error_when_manifest_is_missing(
    tmp_path: Path,
) -> None:
    # Given: an otherwise valid root build directory without a Vite manifest.
    build_dir = tmp_path / "build" / "web"
    build_dir.mkdir(parents=True)

    # When: Core discovers the Web build output.
    with pytest.raises(WebBuildManifestMissingError, match="manifest.json"):
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


def test_discover_web_build_accepts_manifest_with_all_page_shells(
    tmp_path: Path,
) -> None:
    # Given: a Vite manifest for all required generated page shells.
    build_dir = tmp_path / "build" / "web"
    build_dir.mkdir(parents=True)
    manifest = """{
      "login.html": {"file": "assets/login.js"},
      "chat.html": {"file": "assets/chat.js"},
      "manage.html": {"file": "assets/manage.js"}
    }"""
    (build_dir / "manifest.json").write_text(manifest, encoding="utf-8")

    # When: Core discovers the Web build output.
    web_build = discover_web_build(build_dir)

    # Then: it receives the generated build location and manifest path.
    assert web_build.directory == build_dir
    assert web_build.manifest_path == build_dir / "manifest.json"


def test_web_build_allows_only_login_assets_before_authentication(tmp_path: Path) -> None:
    # Given: login imports its own entry plus one shared asset.
    build_dir = tmp_path / "build" / "web"
    assets = build_dir / "assets"
    assets.mkdir(parents=True)
    (build_dir / "login.html").write_text("login", encoding="utf-8")
    (assets / "login.js").write_text("login", encoding="utf-8")
    (assets / "shared.js").write_text("shared", encoding="utf-8")
    (assets / "chat.js").write_text("chat", encoding="utf-8")
    (build_dir / "manifest.json").write_text(
        """{
          "login.html": {"file": "assets/login.js", "imports": ["shared"]},
          "chat.html": {"file": "assets/chat.js"},
          "manage.html": {"file": "assets/manage.js"},
          "shared": {"file": "assets/shared.js"}
        }""",
        encoding="utf-8",
    )

    # When: Core reads the manifest-derived asset visibility.
    web_build = discover_web_build(build_dir)

    # Then: only the anonymous shell's transitive assets are whitelisted.
    assert web_build.is_login_asset("assets/login.js") is True
    assert web_build.is_login_asset("assets/shared.js") is True
    assert web_build.is_login_asset("assets/chat.js") is False
    assert web_build.asset_path("assets/chat.js").read_text() == "chat"
