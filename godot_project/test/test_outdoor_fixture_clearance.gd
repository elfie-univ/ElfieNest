extends SceneTree
## Check placed regional fixtures, not the retired standalone lighting layout.
const LAYOUT := preload("res://tools/outdoor_lighting_layout.gd")
const SUPPORT := preload("res://test/split_estate_test_support.gd")
var failures: Array[String] = []

func _initialize() -> void: call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func run() -> void:
	create_timer(100.0, true, false, true).timeout.connect(func(): quit(1))
	var triangles: Array[PackedVector2Array] = [PackedVector2Array([Vector2(0,0),Vector2(2,0),Vector2(0,2)])]
	check(LAYOUT.footprint_overlaps(Vector3(0.5,0,0.5),triangles), "Fixture inside paving must be rejected")
	check(LAYOUT.footprint_overlaps(Vector3(0.5,0,-0.1),triangles), "Fixture shield must clear the road edge")
	check(not LAYOUT.footprint_overlaps(Vector3(0.5,0,-0.4),triangles), "Clear fixture must remain accepted")
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var fixtures := {}
	var mesh_frames := {}
	var mesh_inputs := {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or mesh.has_meta("source_geometry_path"): continue
		mesh_frames[mesh] = mesh.global_transform
		mesh_inputs[mesh] = mesh.mesh
		var extras: Dictionary = mesh.get_meta("extras", {})
		var id := str(extras.get("outdoor_fixture_id", ""))
		if id.is_empty() or id == "retained-fixture": continue
		if not fixtures.has(id): fixtures[id] = []
		fixtures[id].append(mesh)
	check(not fixtures.has("L24"), "Reported road-junction fixture must remain excluded")
	var outer_count := 0
	var light_count := 0
	for id: String in fixtures:
		if id.begins_with("O"): outer_count += 1
		for mesh: MeshInstance3D in fixtures[id]:
			var extras: Dictionary = mesh.get_meta("extras", {})
			for light: Dictionary in extras.get("design_lights", []):
				light_count += 1
				var emitter := Vector3(light.position[0], light.position[1], light.position[2])
				var target := Vector3(light.target[0], light.target[1], light.target[2])
				check(float(light.distance) > 0.0 and emitter != target, "Fixture has an invalid authored beam: " + id)
				if id == "H01":
					check(float(light.angle) <= deg_to_rad(47.0) and float(light.distance) <= 13.0, "Waterfront beam must fit its platform")
				if id in ["B01", "B02"]:
					check(mesh.get_aabb().grow(0.01).has_point(emitter), "Approach emitter left its real diffuser: " + id)
					check(Vector2(emitter.x-target.x,emitter.z-target.z).is_zero_approx() and target.y < emitter.y, "Approach beam must point downward: " + id)
					check(float(light.angle) <= deg_to_rad(78.0) and extras.design_lights.size() == 1, "Approach fixture must retain one bounded source: " + id)
	check(outer_count >= 4 and light_count > 0, "Regional outer lamps or authored light inputs are missing")
	for id: String in ["H01", "B01", "B02", "G1", "P05"]:
		check(fixtures.has(id), "Approved waterfront/approach/plaza fixture is missing: " + id)
	var bench_count := 0
	for mesh: MeshInstance3D in estate.find_children("Lakeside*", "MeshInstance3D", true, false):
		if not ("bench" in str(mesh.name) or str(mesh.name).begins_with("Lakeside back frame")): continue
		bench_count += 1
		check(mesh.global_basis.y.normalized().is_equal_approx(Vector3.UP), "Placed bench component must remain upright")
	check(bench_count == 9, "Retain all nine placed bench parts")
	# Day/night controls must not move poles, benches, paving or shared geometry.
	var control := preload("res://nest/rendering/estate_lighting.gd").new()
	control.bind(estate)
	control.apply(false)
	control.apply(true)
	for mesh: MeshInstance3D in mesh_frames:
		check(mesh.global_transform == mesh_frames[mesh] and mesh.mesh == mesh_inputs[mesh], "Lighting changed placed geometry: " + str(mesh.name))
	var canonical_error := SUPPORT.batch_error(estate)
	check(canonical_error.is_empty(), canonical_error)
	for message: String in failures: push_error(message)
	print("OUTDOOR_FIXTURE_CLEARANCE fixtures=", fixtures.size(), " sources=", light_count, " outer=", outer_count, " bench_parts=", bench_count, " failures=", failures.size())
	estate.free()
	quit(0 if failures.is_empty() else 1)
