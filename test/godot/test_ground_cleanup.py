"""Terrain owns continuous soil; paving can be hidden without leaving roadbeds."""

from pathlib import Path

from test.godot.test_courtyard_component_geometry import (
    closed_edges,
    faces,
    mesh_nodes,
    model,
)


def test_soil_contains_no_paving_or_artificial_contact_collar():
    source = model("shared-ground")
    node = source.doc["nodes"][mesh_nodes(source)["COMPLETE Building garden island"]]
    primitives = source.doc["meshes"][node["mesh"]]["primitives"]
    materials = [source.doc["materials"][p["material"]]["name"] for p in primitives]
    assert not any("aggregate" in name.lower() for name in materials)
    assert not any("collar" in name.lower() for name in materials)


def test_connector_roadbed_is_an_independent_closed_body():
    source = model("shared-ground")
    name = "Fountain connector paving foundation"
    assert name in mesh_nodes(source)
    edges, directions = closed_edges(faces(source, name))
    assert set(edges.values()) == {2}
    assert all(directions[a, b] == directions[b, a] == 1 for a, b in edges)


def test_water_has_no_unnecessary_interior_grid():
    source = model("lake")
    triangles = list(faces(source, "COMPLETE Inset natural lake"))
    edges, _ = closed_edges(triangles)
    boundary = {point for edge, count in edges.items() if count == 1 for point in edge}
    vertices = {tuple(round(v, 5) for v in point) for tri in triangles for point in tri}
    assert len(vertices - boundary) <= 2
    # A triangulated shoreline with no internal grid needs N - 2 faces.
    assert len(triangles) == len(boundary) - 2
    assert set(edges.values()) == {1, 2}


def test_contact_surfaces_do_not_generate_automatic_approximate_lods():
    root = Path(__file__).resolve().parents[2] / "godot_project/nest/courtyard/parts"
    for asset in ("ground/shared-ground", "waterside/lake"):
        options = (root / (asset + ".glb.import")).read_text()
        assert "meshes/generate_lods=false" in options
