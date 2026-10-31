extends SceneTree

const SAMPLE := preload("res://rooms/estate/estate_lighting_sample.gd")
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func run() -> void:
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var rim := estate.find_child("WholeLakeConcealedRim", true, false) as MeshInstance3D
	check(rim != null and not rim.visible, "The old thin rim must not double the broad bank light")
	var banks: Array[MeshInstance3D] = []
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if str((mesh.get_meta("extras", {}) as Dictionary).get("outdoor_fixture_id", "")) == "shoreline-wash":
			banks.append(mesh)
	check(banks.size() == 7, "All bank components and the waterfront platform must carry the same water-facing finish")
	for bank: MeshInstance3D in banks:
		var original := bank.mesh.surface_get_material(0) as BaseMaterial3D
		var actual := bank.get_active_material(0) as BaseMaterial3D
		check(actual != null and actual.emission_enabled and actual.emission_on_uv2 and actual.emission_texture != null, "The actual water-facing bank must carry a graded light finish, not only a horizontal strip")
		check(actual != null and actual.albedo_color == original.albedo_color and actual.albedo_texture == original.albedo_texture, "The bank must retain its original moss/soil finish")
		check(bool(bank.mesh.surface_get_format(0) & Mesh.ARRAY_FORMAT_TEX_UV2), "Bank lighting must preserve original UVs and use a separate height mask")
		if actual != null and actual.emission_texture != null:
			check(actual.emission_operator == BaseMaterial3D.EMISSION_OP_MULTIPLY, "The height mask must multiply the emitter, leaving the lower bank dark")
			var mask := actual.emission_texture.get_image()
			check(mask.get_pixel(15, 63).r > 0.9 and mask.get_pixel(15, 0).r < 0.01 and mask.get_pixel(0, 63).r < 0.01, "The shore face must fade toward the water and leave non-facing soil unlit")
			var reference := estate.find_child("CY R003 corrected CY R002 continuous natural shore slope 0", true, false) as MeshInstance3D
			var bounds := reference.global_transform * reference.get_aabb()
			var lake := estate.find_child("COMPLETE Inset natural lake", true, false) as MeshInstance3D
			var water_y := (lake.global_transform * lake.get_aabb()).end.y
			var water_row := floori((water_y - bounds.position.y) / bounds.size.y * 63.0)
			check(mask.get_pixel(15, water_row).r < 0.02, "The graded bank must be dark at and below the actual waterline")
	check(int(estate.get_meta("shore_retreat_count", 0)) > 0, "Overhanging land plants must actually retreat from the water")
	check(int(estate.get("multimesh_instance_count")) == 214448, "Shore tidying must preserve all landscape instances")
	var outline: PackedVector3Array = estate.find_child("OutdoorLighting", true, false).get_meta("shoreline")
	var water := PackedVector2Array()
	for i in range(outline.size() - 1): water.append(Vector2(outline[i].x, outline[i].z))
	var lake_bounds := Rect2(water[0], Vector2.ZERO)
	for point: Vector2 in water: lake_bounds = lake_bounds.expand(point)
	for batch: MultiMeshInstance3D in estate.find_children("*", "MultiMeshInstance3D", true, false):
		var mesh := batch.multimesh.mesh
		var selected := false
		for surface in range(mesh.get_surface_count()):
			if str(mesh.surface_get_material(surface).resource_name).begins_with("Layered low groundcover"): selected = true
		if not selected: continue
		for i in range(batch.multimesh.instance_count):
			var pose := batch.global_transform * batch.multimesh.get_instance_transform(i)
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
	for failure: String in failures: push_error(failure)
	if failures.is_empty(): print("PASS real graded shore faces, original soil finish, cleared water footprint, preserved planting and day/night switching; retreated=", estate.get_meta("shore_retreat_count"))
	estate.free()
	quit(0 if failures.is_empty() else 1)
