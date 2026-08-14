from __future__ import annotations

import pytest

from devtools.elfie_lab.app import create_app

from .food_test_helpers import seed_mock_food

PNG = b"\x89PNG\r\n\x1a\n" + b"elfie-lab-vision"
PDF = b"%PDF-1.7\nelfie-lab-attachment"


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
    runtime_dir = tmp_path / "runtime"
    seed_mock_food(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
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
        json={
            "source_domain": "embodied",
            "message": "",
            "food_key": "mock",
            "vision_media_id": descriptor["media_id"],
        },
    )

    assert turn.status_code == 200
    payload = turn.json()
    assert (
        payload["stimulus_bundle"]["vision_media"]["media_id"] == descriptor["media_id"]
    )
    assert payload["trace"]["stages"]["typed_input"]["modalities"] == [
        "vision",
        "environment",
    ]
    assert "data:image" not in str(payload)
    assert str(tmp_path) not in str(payload)


@pytest.mark.parametrize(
    ("filename", "content", "upload_mime", "stored_mime"),
    [
        ("notes.pdf", PDF, "application/pdf", "application/pdf"),
        ("photo.png", PNG, "image/png", "image/png"),
    ],
)
def test_upload_and_submit_communication_attachment(
    tmp_path,
    client_for,
    filename,
    content,
    upload_mime,
    stored_mime,
):
    runtime_dir = tmp_path / "runtime"
    seed_mock_food(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json=elfie_payload("附件测试")).json()
    elfie_id = created["elfie_id"]

    uploaded = client.post(
        f"/api/elfies/{elfie_id}/media",
        files={"file": (filename, content, upload_mime)},
    )

    assert uploaded.status_code == 201
    descriptor = uploaded.json()
    assert descriptor["mime_type"] == stored_mime

    turn = client.post(
        f"/api/elfies/{elfie_id}/turns",
        json={
            "source_domain": "communication",
            "message": "请看看附件",
            "food_key": "mock",
            "attachments": [{"media_id": descriptor["media_id"], "filename": filename}],
        },
    )

    assert turn.status_code == 200
    payload = turn.json()
    assert payload["stimulus_bundle"]["message_attachments"][0]["filename"] == filename
    assert payload["trace"]["stages"]["typed_input"]["modalities"] == [
        "text",
        "attachment",
    ]


def test_turn_rejects_cross_elfie_media_reference(tmp_path, client_for):
    runtime_dir = tmp_path / "runtime"
    seed_mock_food(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    first = client.post("/api/elfies", json=elfie_payload("视觉甲")).json()
    second = client.post("/api/elfies", json=elfie_payload("视觉乙")).json()
    uploaded = client.post(
        f"/api/elfies/{first['elfie_id']}/media",
        files={"file": ("image.png", PNG, "image/png")},
    ).json()

    response = client.post(
        f"/api/elfies/{second['elfie_id']}/turns",
        json={
            "source_domain": "embodied",
            "message": "",
            "food_key": "mock",
            "vision_media_id": uploaded["media_id"],
        },
    )

    assert response.status_code == 404


def test_turn_rejects_malformed_media_id_without_server_error(tmp_path, client_for):
    runtime_dir = tmp_path / "runtime"
    seed_mock_food(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))
    created = client.post("/api/elfies", json=elfie_payload("视觉边界")).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={
            "source_domain": "embodied",
            "message": "",
            "food_key": "mock",
            "vision_media_id": "../../secret",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "无效的媒体标识"}
