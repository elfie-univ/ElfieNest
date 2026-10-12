"""Behavior checks for the approved single set of preview controls."""

import subprocess
from pathlib import Path


def test_control_state_transitions_and_bookmarks() -> None:
    source = Path(__file__).with_name("control-state.test.mjs")
    subprocess.run(["node", "--test", str(source)], check=True)


def test_sample_shortcuts_and_duplicate_object_menu_are_removed() -> None:
    web = Path(__file__).resolve().parents[3] / "devtools/asset_design/web"
    page = (web / "viewer.html").read_text()
    for name in ("bedSample", "nookClose", "nookWindow", "windowView"):
        assert f'id="{name}"' not in page
    assert "适配视图" in page
    assert "查看对象" in page
    assert "预览内容" in (web / "index.html").read_text()
