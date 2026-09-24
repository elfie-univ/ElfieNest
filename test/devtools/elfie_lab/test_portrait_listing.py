from pathlib import Path

from devtools.elfie_lab.app import create_app


def test_list_elfies_includes_saved_portrait_url(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    created = client.post(
        "/api/elfies",
        json={
            "name": "头像列表测试",
            "species_id": "dog",
            "age_years": 2.0,
            "description": "用于验证头像列表",
            "personality_description": "温柔、安静，也很爱探索",
            "appearance_description": "浅色毛发，耳尖颜色较深",
        },
    ).json()
    elfie_id = created["elfie_id"]
    client.app.state.storage.save_portrait(
        elfie_id,
        b"\x89PNG\r\n\x1a\n" + b"portrait-test",
    )

    response = client.get("/api/elfies")

    assert response.status_code == 200
    assert response.json()["items"][0]["portrait_url"] == (
        f"/api/elfies/{elfie_id}/portrait"
    )


def test_godot_browser_capture_uses_the_png_portrait_api_contract():
    source = (
        Path(__file__).resolve().parents[3] / "godot_project/runtime/lab/lab_runtime.gd"
    ).read_text(encoding="utf-8")

    assert "target.toDataURL('image/png')" in source
    assert 'data_url.begins_with("data:image/png;base64,")' in source
    assert "var portrait_height := 512" in source
    assert "const side = Math.min(canvas.width, canvas.height);" in source
    assert (
        "context.drawImage(canvas, x, y, side, side, 0, 0, target.width, target.height);"
        in source
    )
