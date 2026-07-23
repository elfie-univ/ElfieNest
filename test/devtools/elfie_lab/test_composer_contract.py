import subprocess
from pathlib import Path

STATIC_ROOT = Path(__file__).parents[3] / "devtools" / "elfie_lab" / "static"


def test_composer_and_api_modules_are_valid_javascript() -> None:
    for filename in ("api.js", "composer.js"):
        source = (STATIC_ROOT / filename).read_text(encoding="utf-8")
        subprocess.run(
            ["node", "--input-type=module", "--check"],
            input=source,
            text=True,
            check=True,
        )


def test_api_uses_multipart_without_overriding_browser_boundary() -> None:
    source = (STATIC_ROOT / "api.js").read_text(encoding="utf-8")

    assert "export async function uploadMedia" in source
    assert "new FormData()" in source
    assert 'form.append("file", file, file.name)' in source
    assert "body instanceof FormData" in source
    assert "MAX_MEDIA_BYTES" in source


def test_composer_contract_covers_layered_stimulus_and_single_image() -> None:
    source = (STATIC_ROOT / "composer.js").read_text(encoding="utf-8")

    for contract in (
        "vision_media_id",
        "is_network_online",
        "impact_direction",
        "is_sleeping",
        "emotions",
        "uploadMedia",
        "URL.createObjectURL",
        "URL.revokeObjectURL",
        "mediaInput",
        "mediaRemove",
        "debugInjectionEnabled",
    ):
        assert contract in source
    assert "if (!debugEnabled()) return injection" in source
    assert "attachedImage" in source


def test_success_reset_keeps_environment_and_clears_one_shot_inputs() -> None:
    source = (STATIC_ROOT / "composer.js").read_text(encoding="utf-8")

    clear_start = source.index("export function clearOneShotInputs")
    clear_end = source.index("export function autoGrow")
    clear_source = source[clear_start:clear_end]
    assert 'el("impactInput").value = "0"' in clear_source
    assert 'el("strokeInput").value = "0"' in clear_source
    assert "removeAttachedImage()" in clear_source
    assert 'el("temperatureInput").value' not in clear_source
    assert 'el("networkOnline").checked' not in clear_source
