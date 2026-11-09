extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	if not require(estate.has_meta("activity_regions"), "Split assembly must own its activity permissions"): return
	var regions: Resource = estate.get_meta("activity_regions")
	var surfaces: Array[Dictionary] = regions.collect_surfaces(estate)
	var counts := {}
	var dorm_positions := {}
	for item: Dictionary in surfaces:
		counts[item.zone] = int(counts.get(item.zone, 0)) + 1
		if not require(item.mesh.mesh != null, "Activity surface must bind current split geometry"): return
		if str(item.zone).begins_with("dorm-"): dorm_positions[item.mesh.global_transform.origin] = true
		if not require(not ("glazing" in str(item.source) or "window reveal" in str(item.source)), "Windows must not become activity surfaces"): return
	if not require(dorm_positions.size() == 8, "Shared room geometry must retain eight distinct placements"): return
	for zone: String in ["central-01", "central-02", "central-03", "central-04", "courtyard", "stairs", "thresholds", "lawn"]:
		if not require(counts.has(zone), "Missing activity zone: " + zone): return
	for ordinal: int in range(1, 9):
		for prefix: String in ["dorm", "terrace"]:
			var zone := "%s-%02d" % [prefix, ordinal]
			if not require(counts.has(zone), "Missing activity instance " + zone + ": " + str(counts)): return
	var access := preload("res://nest/estate/estate_outdoor_access.gd").new()
	root.add_child(access)
	if not require(access.build(estate), "Split outdoor permissions must build without loading the merged world"): return
	if not require(access.contains_point(Vector2(0, 20)), "Plaza approach must stay accessible"): return
	if not require(access.contains_point(Vector2(0, 0)), "The entrance must connect the ground floor to the plaza"): return
	if not require(access.contains_outdoor_point(Vector2(0, 40)), "Open front lawn must stay accessible"): return
	if not require(not access.contains_point(Vector2(100, 100)), "Outside the estate must be inaccessible"): return
	var checked_water := false
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or regions.source_name(mesh) != "COMPLETE Inset natural lake": continue
		var arrays := mesh.mesh.surface_get_arrays(0)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var sample := Vector3.ZERO
		for i: int in range(3): sample += mesh.global_transform * vertices[indices[i] if not indices.is_empty() else i] / 3.0
		if not require(not access.contains_point(Vector2(sample.x, sample.z)), "Actual split lake water must stay inaccessible"): return
		checked_water = true
	if not require(checked_water, "The current split lake must be checked"): return
	var invalid: Resource = regions.duplicate(true)
	invalid.outdoor_permissions.erase("lawn")
	var rejected := preload("res://nest/estate/estate_outdoor_access.gd").new()
	if not require(not invalid.populate_outdoor(rejected, estate), "Missing activity permissions must fail closed"): return
	rejected.free()
	var geometry := NavigationMeshSourceGeometryData3D.new()
	for item: Dictionary in surfaces:
		var mesh: MeshInstance3D = item.mesh
		geometry.add_mesh(mesh.mesh, mesh.global_transform)
	if not require(geometry.get_vertices().size() > 0, "All activity zones must export actual navigation input"): return
	var report := {"zones": counts, "surfaces": surfaces.size(), "outdoor_boundary_segments": access.boundary_segments.size(), "navigation_input_vertices": geometry.get_vertices().size() / 3}
	var file := FileAccess.open("res://../build/godot_assets/split-activity/check.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	print("PASS split activity source ", JSON.stringify(report))
	estate.free()
	access.free()
	quit(0)
