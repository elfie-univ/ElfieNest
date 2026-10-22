"""Behavior checks for the approved single set of preview controls."""

import subprocess
from html.parser import HTMLParser
from pathlib import Path


def test_control_state_transitions_and_bookmarks() -> None:
    source = Path(__file__).with_name("control-state.test.mjs")
    media = source.with_name("media.test.mjs")
    subprocess.run(["node", "--test", str(source), str(media)], check=True)


def test_sample_shortcuts_and_duplicate_object_menu_are_removed() -> None:
    web = Path(__file__).resolve().parents[3] / "devtools/asset_design/web"
    page = (web / "viewer.html").read_text()
    for name in ("bedSample", "nookClose", "nookWindow", "windowView"):
        assert f'id="{name}"' not in page
    assert "适配视图" in page
    assert "查看对象" in page
    index = (web / "index.html").read_text()
    toolbar = index.split('<section class="workspace-toolbar"', 1)[1].split(
        "</section>", 1
    )[0]
    assert '<select id="categorySelect"' in toolbar
    assert 'id="furnitureSelect"' not in toolbar
    assert 'id="furniturePicker"' not in toolbar
    assert 'id="markAsset"' not in index
    assert 'id="deleteAsset"' not in toolbar
    selection = index.split('<section class="selection"', 1)[1].split("</section>", 1)[
        0
    ]
    assert 'id="deleteAsset"' in selection
    assert 'class="selection-actions"' in selection
    assert 'id="designSelect"' not in toolbar
    assert '<select id="assetSelect"' in toolbar
    assert 'aria-label="版本" disabled' in toolbar
    for removed in ("<dialog", 'id="search"', 'id="openAssets"', 'id="versionGrid"'):
        assert removed not in index
    script = (web / "library.js").read_text()
    assert "method:'DELETE'" in script
    assert ".showModal()" not in script
    assert 'id="mediaModes"' in index
    assert 'id="comparison"' in index
    assert 'id="categories"' not in index


def test_version_actions_share_the_information_area_and_sidebar_order() -> None:
    web = Path(__file__).resolve().parents[3] / "devtools/asset_design/web"
    index = (web / "index.html").read_text()
    toolbar = index.split('<section class="workspace-toolbar"', 1)[1].split(
        "</section>", 1
    )[0]
    selection = index.split('<section class="selection"', 1)[1].split("</section>", 1)[
        0
    ]
    assert 'id="confirmVersion"' not in toolbar
    for control in (
        "assetDescription",
        "confirmVersion",
        "deleteAsset",
        "deleteConfirm",
        "deleteCancel",
    ):
        assert f'id="{control}"' in selection

    class SidebarOrder(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.controls = []

        def handle_starttag(self, tag, attrs) -> None:
            identifier = dict(attrs).get("id")
            if identifier:
                self.controls.append(identifier)

    parser = SidebarOrder()
    parser.feed((web / "viewer.html").read_text())
    ordered = (
        "module",
        "floor",
        "interiorView",
        "exteriorView",
        "whole",
        "section",
        "glass",
        "context",
        "scale",
        "dimensions",
        "ruler",
        "zoomOut",
        "reset",
        "zoomIn",
        "front",
        "top",
        "rear",
        "side",
        "day",
        "dusk",
        "download",
    )
    positions = [parser.controls.index(control) for control in ordered]
    assert positions == sorted(positions)


def test_download_and_explanations_are_below_the_viewer_controls() -> None:
    web = Path(__file__).resolve().parents[3] / "devtools/asset_design/web"
    page = (web / "viewer.html").read_text()
    sidebar = page.split("<aside>", 1)[1].split("</aside>", 1)[0]
    for identifier in ("download", "modelName", "modelSize"):
        assert f'id="{identifier}"' not in sidebar
    assert 'class="help"' not in sidebar
    footer = page.split('<footer class="viewer-footer">', 1)[1].split("</footer>", 1)[0]
    for identifier in ("download", "modelName", "modelSize"):
        assert f'id="{identifier}"' in footer
    assert "<summary>操作说明</summary>" in footer


def test_version_description_is_a_collapsed_disclosure() -> None:
    web = Path(__file__).resolve().parents[3] / "devtools/asset_design/web"
    page = (web / "index.html").read_text()
    disclosure = page.split('<details id="descriptionDetails"', 1)[1].split(
        "</details>", 1
    )[0]
    assert "open" not in disclosure.split(">", 1)[0]
    summary = disclosure.split("<summary>", 1)[1].split("</summary>", 1)[0]
    assert 'id="assetDescription"' in summary


def test_embedded_viewer_sizes_both_panels_from_the_controls() -> None:
    web = Path(__file__).resolve().parents[3] / "devtools/asset_design/web"
    page = (web / "viewer.html").read_text()
    sidebar = page.split("<aside>", 1)[1].split("</aside>", 1)[0]
    assert '<div id="viewerControls">' in sidebar
    assert sidebar.index('id="viewerControls"') < sidebar.index('id="scopeControls"')
    assert 'id="dusk"' in sidebar
    assert 'id="courtyardViewControls"' in sidebar
    viewer = (web / "viewer.js").read_text()
    assert "notify('asset-layout'" in viewer.split("try{", 1)[0]
    library = (web / "library.js").read_text()
    assert "data.type==='asset-layout'" in library
