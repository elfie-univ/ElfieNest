from fastapi.testclient import TestClient

from devtools.nest_lab.app import create_app
from devtools.nest_lab.world import NestLabWorld
from infrastructure.godot.gateway.messages import CommandName
from test.devtools.nest_lab.test_world import _LabGateway, _saved_actors


def test_actor_generation_edit_and_delete_use_isolated_lab_state(tmp_path) -> None:
    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")
    created = client.post(
        "/api/actors", json={"species": "saevi", "age_years": 5, "gender": "female"}
    )
    assert created.status_code == 201
    actor = created.json()
    assert actor["age_years"] == 5
    assert actor["gender"] == "female"
    species = client.get("/api/actor-species").json()["items"]
    assert {item["id"] for item in species} == {"saevi", "tovren"}
    edited = client.put(
        f"/api/actors/{actor['actor_id']}",
        json={"species": "tovren", "age_years": 8, "gender": "male"},
    )
    assert actor["saved"] is True
    assert edited.status_code == 409
    assert client.get("/api/actors").json()["items"][0]["species"] == "saevi"
    assert client.delete(f"/api/actors/{actor['actor_id']}").status_code == 200
    assert client.get("/api/actors").json()["items"] == []
    assert client.delete(f"/api/actors/{actor['actor_id']}").status_code == 409


def test_invalid_age_does_not_add_an_actor(tmp_path) -> None:
    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")
    response = client.post(
        "/api/actors", json={"species": "saevi", "age_years": 999, "gender": "female"}
    )
    assert response.status_code == 422
    assert client.get("/api/actors").json()["items"] == []


def test_generated_appearance_reaches_existing_actor_sync_and_deletion(
    tmp_path,
) -> None:
    gateway = _LabGateway()
    gateway.connect()
    world = NestLabWorld(
        data_dir=tmp_path,
        http_port=8890,
        websocket_port=8891,
        gateway=gateway,
        saved_actors=_saved_actors(tmp_path),
    )
    world.poll()
    actor = world.add_actor("saevi", age_years=5, gender="female")
    syncs = [
        payload
        for name, payload, _ in gateway.commands
        if name is CommandName.SYNC_ACTORS
    ]
    appearance = syncs[-1]["actors"][0]["appearance"]
    assert appearance["species_id"] == "saevi"
    assert appearance["bone_scales"]
    assert appearance["material_parameters"]
    assert appearance == actor.appearance.to_payload()
    world.remove_actor(actor.actor_id)
    syncs = [
        payload
        for name, payload, _ in gateway.commands
        if name is CommandName.SYNC_ACTORS
    ]
    assert syncs[-1]["actors"] == []
