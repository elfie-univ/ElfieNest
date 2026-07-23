from __future__ import annotations

from devtools.elfie_lab.app import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"elfie-lab-vision"


def elfie_payload(name):
    return {
        "name": name,
        "species_id": "fox",
        "age_years": 2,
        "description": "验证视觉输入",
        "personality_description": "温柔、好奇",
        "appearance_description": "浅色毛发",
    }


def test_upload_and_submit_pure_visual_turn(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    created = client.post("/api/elfies", json=elfie_payload("视觉测试")).json()
    elfie_id = created["elfie_id"]

    uploaded = client.post(
        f"/api/elfies/{elfie_id}/media",
        files={"file": ("ignored.txt", PNG, "text/plain")},
    )

    assert uploaded.status_code == 201
    descriptor = uploaded.json()
    assert descriptor["mime_type"] == "image/png"
    assert str(tmp_path) not in descriptor["uri"]

    turn = client.post(
        f"/api/elfies/{elfie_id}/turns",
        json={"message": "", "food_key": "mock", "vision_media_id": descriptor["media_id"]},
    )

    assert turn.status_code == 200
    payload = turn.json()
    assert payload["stimulus_bundle"]["vision_media"]["media_id"] == descriptor["media_id"]
    assert payload["trace"]["stages"]["typed_input"]["modalities"] == [
        "vision",
        "environment",
    ]
    assert "data:image" not in str(payload)
    assert str(tmp_path) not in str(payload)


def test_turn_rejects_cross_elfie_media_reference(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    first = client.post("/api/elfies", json=elfie_payload("视觉甲")).json()
    second = client.post("/api/elfies", json=elfie_payload("视觉乙")).json()
    uploaded = client.post(
        f"/api/elfies/{first['elfie_id']}/media",
        files={"file": ("image.png", PNG, "image/png")},
    ).json()

    response = client.post(
        f"/api/elfies/{second['elfie_id']}/turns",
        json={
            "message": "",
            "food_key": "mock",
            "vision_media_id": uploaded["media_id"],
        },
    )

    assert response.status_code == 404


def test_turn_rejects_malformed_media_id_without_server_error(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    created = client.post("/api/elfies", json=elfie_payload("视觉边界")).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"message": "", "food_key": "mock", "vision_media_id": "../../secret"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "无效的媒体标识"}
