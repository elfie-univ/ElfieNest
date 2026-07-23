from pathlib import Path

STATIC_DIR = Path(__file__).parents[3] / "devtools" / "elfie_lab" / "static"


def test_elfie_menu_renders_real_portrait_name_and_delete_command() -> None:
    # Given
    source = (STATIC_DIR / "elfie-menu.js").read_text(encoding="utf-8")

    # When / Then
    assert 'import { api } from "./api.js";' in source
    assert "createPortraitThumbnail" in source
    assert "elfie.name" in source
    assert 'method: "DELETE"' in source
    assert "encodeURIComponent(elfie.elfie_id)" in source
    assert 'aria-label", `删除${elfie.name}`' in source
    assert ".innerHTML" not in source


def test_elfie_menu_exposes_confirmation_and_result_callbacks() -> None:
    # Given
    source = (STATIC_DIR / "elfie-menu.js").read_text(encoding="utf-8")

    # When / Then
    for callback in (
        "onConfirmDelete",
        "onDeleted",
        "onDeleteError",
        "onEmpty",
        "onSelect",
    ):
        assert callback in source
    assert "window.confirm" in source


def test_delete_success_switches_to_next_or_clears_selected_elfie() -> None:
    # Given
    source = (STATIC_DIR / "elfie-menu.js").read_text(encoding="utf-8")

    # When / Then
    assert "result.next_elfie_id" in source
    assert "await callbacks.onSelect(result.next_elfie_id)" in source
    assert "state.currentId = null" in source
    assert "state.session = null" in source
    assert 'localStorage.removeItem("elfieLab.currentElfie")' in source
    assert "callbacks.onEmpty()" in source
    assert "ui.elfieEmpty.hidden = false" in source
    assert "ui.elfieContent.hidden = true" in source
    assert "ui.switcherWrap.hidden = true" in source
    api_call = source.index('method: "DELETE"')
    list_mutation = source.index("state.elfies = state.elfies.filter")
    assert api_call < list_mutation


def test_portrait_module_owns_thumbnail_and_current_switcher_sync() -> None:
    # Given
    source = (STATIC_DIR / "portrait.js").read_text(encoding="utf-8")

    # When / Then
    assert "export function elfiePortraitUrl" in source
    assert "export function createPortraitThumbnail" in source
    assert "export function syncCurrentElfiePortrait" in source
    assert 'el("miniAvatar")' in source
    assert "createPortraitThumbnail(profile, 40)" in source
    assert "elfie.portrait_url" in source
    assert 'image.addEventListener("error"' in source
    assert 'image.addEventListener("load"' in source
    assert ".innerHTML" not in source
