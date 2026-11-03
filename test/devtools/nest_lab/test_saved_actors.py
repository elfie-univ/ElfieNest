import pytest
from fastapi.testclient import TestClient

from devtools.elfie_lab.app import create_unified_app
from devtools.elfie_lab.storage import ElfieLabStorage
from devtools.nest_lab.saved_actors import SavedLabActors
from devtools.nest_lab.world import NestLabWorld
from elfie.profile import AppearanceResolver
from infrastructure.godot.gateway.messages import CommandName
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from test.devtools.nest_lab.test_world import _LabGateway


def test_saved_elfies_are_reused_after_restart_without_recreating_appearance(tmp_path):
    storage = ElfieLabStorage(str(tmp_path / "elfie_lab"))
    spec = storage.create_elfie("已保存的赛维", "saevi", 5, gender="female")
    profile_path = storage.elfie_dir(spec.elfie_id) / "profile"
    profile = YamlProfileStoreAdapter(profile_path).load()
    original = (profile_path / "profile.yaml").read_bytes()
    gateway = _LabGateway()
    gateway.connect()

    def make_world():
        return NestLabWorld(
            data_dir=tmp_path / "nest_lab",
            http_port=8890,
            websocket_port=8891,
            gateway=gateway,
            saved_actors=SavedLabActors(storage),
        )

    world = make_world()
    (actor,) = world.actors()
    assert actor.actor_id == spec.elfie_id
    assert actor.name == spec.name
    assert actor.saved
    assert actor.appearance == AppearanceResolver().resolve(profile)
    sync = [
        payload
        for name, payload, _ in gateway.commands
        if name is CommandName.SYNC_ACTORS
    ][-1]
    assert sync["actors"][0]["appearance"] == actor.appearance.to_payload()
    world.remove_actor(actor.actor_id)
    assert world.actors() == ()
    assert storage.list_elfies()[0].elfie_id == spec.elfie_id
    assert world.restore_saved_actors() == (actor,)
    assert make_world().actors()[0] == actor
    assert (profile_path / "profile.yaml").read_bytes() == original


def test_unified_nest_lists_new_saved_elfies_and_does_not_edit_their_profiles(tmp_path):
    app = create_unified_app(tmp_path)
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/actors").json()["items"] == []
    spec = app.state.storage.create_elfie("共享实验精灵", "tovren", 5, gender="male")
    actors = client.get("/api/actors").json()["items"]
    assert actors[0]["actor_id"] == spec.elfie_id
    assert actors[0]["name"] == spec.name
    assert actors[0]["saved"] is True
    assert len(client.get("/api/actors").json()["items"]) == 1
    response = client.put(
        f"/api/actors/{spec.elfie_id}",
        json={"species": "saevi", "age_years": 5, "gender": "female"},
    )
    assert response.status_code == 409
    assert app.state.storage.list_elfies()[0].species_id == "tovren"
    assert client.delete(f"/api/actors/{spec.elfie_id}").status_code == 200
    assert client.get("/api/actors").json()["items"] == []
    restored = client.post("/api/actors/restore-saved")
    assert restored.status_code == 200
    assert restored.json()["items"][0]["actor_id"] == spec.elfie_id


def test_default_unified_entry_respects_existing_elfie_lab_data_override(
    tmp_path, monkeypatch
):
    existing = tmp_path / "shared-experiments"
    monkeypatch.setenv("ELFIE_LAB_DATA_DIR", str(existing))
    monkeypatch.setenv("ELFIE_DEV_HOME", str(tmp_path / "developer"))
    app = create_unified_app()
    assert app.state.storage.root == existing.resolve()
    explicit = create_unified_app(tmp_path / "explicit")
    assert (
        explicit.state.storage.root == (tmp_path / "explicit" / "elfie_lab").resolve()
    )


@pytest.mark.parametrize("local", [False, True])
def test_nest_created_elfie_is_shared_and_survives_service_restart(
    tmp_path, monkeypatch, local
):
    root = tmp_path / ("local" if local else "global")
    monkeypatch.setenv("ELFIE_DEV_HOME", str(tmp_path / "global"))

    def make_app():
        return create_unified_app(root) if local else create_unified_app()

    app = make_app()
    client = TestClient(app, base_url="http://127.0.0.1")
    result = client.post(
        "/api/actors",
        json={
            "name": "复用测试精灵",
            "species": "saevi",
            "age_years": 5,
            "gender": "female",
        },
    )
    assert result.status_code == 201
    actor = result.json()
    assert actor["saved"] is True
    assert actor["name"] == "复用测试精灵"
    assert client.get("/api/elfies").json()["items"][0]["elfie_id"] == actor["actor_id"]
    profile = (
        app.state.storage.elfie_dir(actor["actor_id"]) / "profile" / "profile.yaml"
    )
    before = profile.read_bytes()
    restarted = TestClient(make_app(), base_url="http://127.0.0.1")
    assert restarted.get("/api/actors").json()["items"] == [actor]
    assert profile.read_bytes() == before
    assert len(restarted.get("/api/elfies").json()["items"]) == 1
    if local:
        global_client = TestClient(create_unified_app(), base_url="http://127.0.0.1")
        assert global_client.get("/api/elfies").json()["items"] == []


def test_failed_save_does_not_leave_an_unsaved_scene_actor(tmp_path, monkeypatch):
    app = create_unified_app(tmp_path)

    def fail_save(*args, **kwargs):
        raise OSError("simulated full disk")

    monkeypatch.setattr(app.state.storage, "create_elfie", fail_save)
    client = TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False)
    response = client.post(
        "/api/actors", json={"species": "saevi", "age_years": 5, "gender": "female"}
    )
    assert response.status_code == 500
    assert client.get("/api/actors").json()["items"] == []
    assert app.state.storage.list_elfies() == []
