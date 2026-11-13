extends SceneTree

const SAMPLE := preload("res://nest/rendering/estate_lighting_sample.gd")
const SHORE := preload("res://nest/courtyard/parts/waterside/estate_shore_finish.gd")
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var rim := estate.find_child("WholeLakeConcealedRim", true, false) as MeshInstance3D
	check(rim != null and not rim.visible, "The old thin rim must not double the broad bank light")
	var ribbon := estate.find_child("WholeLakeRibbon", true, false) as MeshInstance3D
	if ribbon == null:
		push_error("The full lake and platform require one shared ribbon")
		estate.free()
		quit(1)
		return
	var banks: Array[MeshInstance3D] = [ribbon]
	check(ribbon.mesh.get_surface_count() == 1, "Shore lighting must use only its original sloping face, without a land cover")
	var path: PackedVector3Array = SHORE.ribbon_path(estate)
	check(path[0] != path[-1], "The real waterfall opening must remain clear")
	var arrays := ribbon.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	check(vertices.size() == path.size() * 4 and indices.size() == (path.size() - 1) * 18, "The sloping face must have no separate horizontal luminous band")
	var base := estate.find_child("GroundPatch_196", true, false) as MeshInstance3D
	check(base != null and base.visible, "The extended original grass face must remain the rendered ground")
	var curtain := estate.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
	var curtain_box := curtain.global_transform * curtain.get_aabb()
	for i in range(0, indices.size(), 3):
		var a := vertices[indices[i]]
		var b := vertices[indices[i + 1]]
		var c := vertices[indices[i + 2]]
		var center := (a + b + c) / 3.0
		check(not (center.x > curtain_box.position.x and center.x < curtain_box.end.x and center.z > curtain_box.position.z and center.z < curtain_box.end.z), "No warm bank-light triangle may cross the waterfall face")
	var edges: Dictionary = {}
	for i in range(0, indices.size(), 3):
		for j in range(3):
			var a := indices[i + j]
			var b := indices[i + (j + 1) % 3]
			var key := Vector2i(mini(a, b), maxi(a, b))
			edges[key] = int(edges.get(key, 0)) + 1
	for key: Vector2i in edges:
		var boundary := (key.x % 4 == 0 and key.y % 4 == 0) or (key.x % 4 == 3 and key.y % 4 == 3) or (key.x / 4 == key.y / 4 and key.x / 4 in [0, path.size() - 1])
		check(int(edges[key]) == (1 if boundary else 2), "Ribbon joins must share vertices, with no cracks, caps or overlapping triangles")
	for i in range(path.size() - 1):
		check(vertices[i * 4 + 1].y - vertices[i * 4 + 3].y > 0.25, "Platform and bank must retain the same broad luminous face")
	var ribbon_material := ribbon.get_active_material(0) as BaseMaterial3D
	var mask := ribbon_material.emission_texture.get_image()
	check(mask.get_pixel(0, 63).r > 0.9 and mask.get_pixel(0, 0).r < 0.01, "The whole ribbon uses the same warm top-to-water fade")
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh == ribbon: continue
		check(str((mesh.get_meta("extras", {}) as Dictionary).get("outdoor_fixture_id", "")) != "shoreline-wash", "Old per-bank glow must not create duplicate contours")
	check(preload("res://test/split_estate_test_support.gd").batch_error(estate).is_empty(), "Every landscape batch must match its canonical placement")
	var shore := preload("res://test/split_estate_test_support.gd").shore_geometry(estate)
	var water: PackedVector2Array = shore.water
	var lake_bounds: Rect2 = shore.water_bounds
	for batch: MultiMeshInstance3D in estate.find_children("*", "MultiMeshInstance3D", true, false):
		var mesh := batch.multimesh.mesh
		var selected := false
		for surface in range(mesh.get_surface_count()):
			if str(mesh.surface_get_material(surface).resource_name).begins_with("Layered low groundcover"): selected = true
		if not selected: continue
		for i in range(batch.multimesh.instance_count):
			var pose := batch.global_transform * preload("res://test/split_estate_test_support.gd").instance_transform(batch, i)
			if not lake_bounds.grow(2.0).has_point(Vector2(pose.origin.x, pose.origin.z)): continue
			var bounds: AABB = pose * mesh.get_aabb()
			for corner in range(8):
				var point := bounds.get_endpoint(corner)
				check(not Geometry2D.is_point_in_polygon(Vector2(point.x, point.z), water), "Retreated shore foliage must leave the actual water footprint clear")
	var sample := SAMPLE.new()
	sample.bind_m01(estate)
	for night in [true, false]:
		sample.apply_environment(0.0 if night else 1.0, night)
		for bank: MeshInstance3D in banks:
			var material := bank.get_active_material(0) as BaseMaterial3D
			if material == null: continue
			check(material.emission_energy_multiplier > 0.0 if night else is_zero_approx(material.emission_energy_multiplier), "Shore illumination must follow the actual night/day switch")
	for failure: String in failures.slice(0, 10): push_error(failure)
	if failures.is_empty(): print("PASS one shared ribbon with clear waterfall opening, uniform profile, manifold joins, no duplicate glow, preserved planting and day/night switching; retreated=", estate.get_meta("shore_retreat_count"))
	estate.free()
	quit(0 if failures.is_empty() else 1)
