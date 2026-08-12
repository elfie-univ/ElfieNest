from fastapi.testclient import TestClient

from devtools.elfie_lab.app import create_app

from .food_test_helpers import seed_mock_food


def complete_elfie_payload(name="测试精灵", species_id="fox"):
    return {
        "name": name,
        "species_id": species_id,
        "age_years": 2.0,
        "description": "用于验证单精灵认知与行为",
        "personality_description": "温柔、安静，也很爱探索",
        "appearance_description": "浅色毛发，耳尖颜色较深",
    }


def test_create_elfie_requires_complete_profile_and_derives_life_stage(
    tmp_path, client_for
):
    # Given
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    payload = complete_elfie_payload("年龄测试", "dog")

    # When
    responses = {
        field: client.post(
            "/api/elfies",
            json={key: value for key, value in payload.items() if key != field},
        )
        for field in (
            "name",
            "species_id",
            "age_years",
            "description",
            "personality_description",
            "appearance_description",
        )
    }
    created = client.post("/api/elfies", json=payload)

    # Then
    assert all(response.status_code == 422 for response in responses.values())
    assert created.status_code == 201
    assert created.json()["profile"]["age_years"] == 2.0
    assert created.json()["profile"]["life_stage"] == "青年"


def test_update_big_five_refreshes_current_session_profile(tmp_path, client_for):
    # Given
    app = create_app(str(tmp_path / "data"), str(tmp_path / "runtime"))
    client = client_for(app)
    created = client.post("/api/elfies", json=complete_elfie_payload()).json()
    elfie_id = created["elfie_id"]

    # When
    updated = client.patch(
        f"/api/elfies/{elfie_id}/personality",
        json={
            "openness": 0.12,
            "conscientiousness": 0.34,
            "extraversion": 0.56,
            "agreeableness": 0.78,
            "neuroticism": 0.9,
        },
    )
    current = client.get(f"/api/elfies/{elfie_id}")

    # Then
    assert updated.status_code == 200
    assert current.json()["profile"]["big_five"] == {
        "openness": 0.12,
        "conscientiousness": 0.34,
        "extraversion": 0.56,
        "agreeableness": 0.78,
        "neuroticism": 0.9,
    }
    assert (
        current.json()["profile"]["personality_derivation"]["provenance"]
        == "description+manual_override"
    )


def test_app_rejects_untrusted_host_for_mutating_requests(tmp_path, client_for):
    # Given
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    # When
    response = client.post(
        "/api/elfies",
        headers={"host": "attacker.example"},
        json=complete_elfie_payload(),
    )

    # Then
    assert response.status_code == 400


def test_app_create_elfie_and_chat(tmp_path, client_for):
    runtime_dir = tmp_path / "runtime"
    seed_mock_food(runtime_dir)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime_dir)))

    assert client.get("/api/health").json()["status"] == "ok"
    created = client.post(
        "/api/elfies",
        json=complete_elfie_payload("Web 测试精灵", "dog"),
    )
    assert created.status_code == 201
    elfie_id = created.json()["elfie_id"]
    assert created.json()["profile"]["species_id"] == "dog"
    assert created.json()["profile"]["appearance"]["species_id"] == "dog"
    assert (
        tmp_path / "data" / "elfies" / elfie_id / "profile" / "profile.yaml"
    ).is_file()

    turn = client.post(
        f"/api/elfies/{elfie_id}/turns",
        json={"source_domain": "communication", "message": "跟我打个招呼", "food_key": "mock"},
    )
    assert turn.status_code == 200
    payload = turn.json()
    assert payload["elfie_id"] == elfie_id
    assert payload["model_call"]["provider"] == "mock"

    restored = client.get(f"/api/elfies/{elfie_id}")
    assert len(restored.json()["turns"]) == 1


def test_create_elfie_derives_personality_and_preserves_appearance_text(
    tmp_path, client_for
):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    response = client.post(
        "/api/elfies",
        json={
            **complete_elfie_payload("描述测试精灵", "fox"),
            "appearance_description": "银白色毛发，耳尖是灰色",
            "personality_description": "温柔、乖巧，也很爱探索",
        },
    )

    assert response.status_code == 201
    profile = response.json()["profile"]
    assert profile["appearance_description"] == "银白色毛发，耳尖是灰色"
    assert profile["personality_description"] == "温柔、乖巧，也很爱探索"
    assert 0.7 <= profile["big_five"]["agreeableness"] <= 0.95
    assert profile["personality_derivation"]["preset"] == "安静温顺"
    assert profile["personality_derivation"]["overridden_traits"] == []


def test_app_lifespan_stops_registered_elfie_sessions(tmp_path):
    app = create_app(str(tmp_path / "data"), str(tmp_path / "runtime"))

    with TestClient(app, base_url="http://127.0.0.1") as client:
        created = client.post(
            "/api/elfies", json=complete_elfie_payload("生命周期测试")
        ).json()
        session = app.state.sessions.get(created["elfie_id"])
        runtime = session.elfie._brain_runtime
        assert runtime is not None
        assert runtime.is_running is True

    assert runtime.is_running is False


def test_app_calls_ready_callback_during_lifespan_startup(tmp_path):
    # Given
    lifecycle_events = []
    app = create_app(
        str(tmp_path / "data"),
        str(tmp_path / "runtime"),
        on_ready=lambda: lifecycle_events.append("ready"),
    )
    assert lifecycle_events == []

    # When
    with TestClient(app, base_url="http://127.0.0.1"):
        events_while_running = list(lifecycle_events)

    # Then
    assert events_while_running == ["ready"]


def test_app_rejects_empty_stimulus(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    created = client.post(
        "/api/elfies", json=complete_elfie_payload("空刺激测试")
    ).json()

    response = client.post(
        f"/api/elfies/{created['elfie_id']}/turns",
        json={"source_domain": "embodied", "message": "", "food_key": "mock"},
    )

    assert response.status_code == 422


def test_app_rejects_unknown_species_and_saves_portrait(tmp_path, client_for):
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    invalid = client.post(
        "/api/elfies",
        json={**complete_elfie_payload("未知物种"), "species_id": "rabbit"},
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/elfies", json=complete_elfie_payload("头像测试", "fox")
    ).json()
    elfie_id = created["elfie_id"]
    png_header = "iVBORw0KGgo="
    saved = client.put(
        f"/api/elfies/{elfie_id}/portrait",
        json={"data_url": f"data:image/png;base64,{png_header}"},
    )
    assert saved.status_code == 200
    image = client.get(saved.json()["portrait_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"


def test_delete_elfie_recycles_data_and_selects_next_elfie(tmp_path, client_for):
    # Given
    data_dir = tmp_path / "data"
    app = create_app(str(data_dir), str(tmp_path / "runtime"))
    client = client_for(app)
    deleted_id = client.post(
        "/api/elfies", json=complete_elfie_payload("待删除")
    ).json()["elfie_id"]
    next_id = client.post("/api/elfies", json=complete_elfie_payload("保留")).json()[
        "elfie_id"
    ]
    (data_dir / "media" / deleted_id).mkdir(parents=True)
    (data_dir / "media" / deleted_id / "sample.txt").write_text("media")

    # When
    response = client.delete(f"/api/elfies/{deleted_id}")

    # Then
    assert response.status_code == 200
    assert response.json() == {
        "deleted_elfie_id": deleted_id,
        "next_elfie_id": next_id,
    }
    assert client.get(f"/api/elfies/{deleted_id}").status_code == 404
    assert [item["elfie_id"] for item in client.get("/api/elfies").json()["items"]] == [
        next_id
    ]
    bundle = next((data_dir / "trash").iterdir())
    assert (bundle / "elfies" / deleted_id / "profile.json").is_file()
    assert (bundle / "media" / deleted_id / "sample.txt").is_file()
    assert (bundle / "manifest.json").is_file()


def test_delete_elfie_returns_not_found_when_absent(tmp_path, client_for):
    # Given
    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    # When
    response = client.delete("/api/elfies/elfie_absent")

    # Then
    assert response.status_code == 404


def test_delete_elfie_returns_conflict_while_turn_is_active(tmp_path, client_for):
    # Given
    app = create_app(str(tmp_path / "data"), str(tmp_path / "runtime"))
    client = client_for(app)
    elfie_id = client.post("/api/elfies", json=complete_elfie_payload("忙碌")).json()[
        "elfie_id"
    ]
    session = app.state.sessions.get(elfie_id)
    session._lock.acquire()

    try:
        # When
        response = client.delete(f"/api/elfies/{elfie_id}")
    finally:
        session._lock.release()

    # Then
    assert response.status_code == 409
    assert app.state.storage.get_elfie(elfie_id).elfie_id == elfie_id


def test_delete_elfie_rejects_invalid_id_without_creating_trash(tmp_path, client_for):
    # Given
    data_dir = tmp_path / "data"
    client = client_for(create_app(str(data_dir), str(tmp_path / "runtime")))

    # When
    response = client.delete("/api/elfies/invalid$id")

    # Then
    assert response.status_code == 404
    assert not (data_dir / "trash").exists()


def test_delete_elfie_reports_recycle_failure_and_restores_source(tmp_path):
    # Given
    data_dir = tmp_path / "data"
    app = create_app(str(data_dir), str(tmp_path / "runtime"))
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        raise_server_exceptions=False,
    ) as client:
        elfie_id = client.post(
            "/api/elfies", json=complete_elfie_payload("回滚")
        ).json()["elfie_id"]
        (data_dir / "sessions" / elfie_id).mkdir(parents=True, exist_ok=True)
        (data_dir / "sessions" / elfie_id / "turn.json").write_text("{}")
        move_count = 0
        original_move = app.state.recycle_store._move_path

        def fail_second_move(source, destination):
            nonlocal move_count
            move_count += 1
            if move_count == 2:
                raise OSError("injected API recycle failure")
            original_move(source, destination)

        app.state.recycle_store._move_path = fail_second_move

        # When
        response = client.delete(f"/api/elfies/{elfie_id}")

        # Then
        assert response.status_code == 500
        assert "删除失败" in response.json()["detail"]
        assert (data_dir / "elfies" / elfie_id / "profile.json").is_file()
        assert client.get(f"/api/elfies/{elfie_id}").status_code == 200
