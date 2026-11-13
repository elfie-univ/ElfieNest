extends SceneTree
## Export activity input from the split world; physical-obstacle baking is separate.

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var regions: Resource = estate.get_meta("activity_regions")
	var access := preload("res://nest/spatial/estate_outdoor_access.gd").new()
	root.add_child(access)
	if not access.build(estate):
		push_error("Cannot export split activity permissions")
		quit(1)
		return
	var geometry := NavigationMeshSourceGeometryData3D.new()
	var counts := {}
	for item: Dictionary in regions.collect_surfaces(estate):
		var mesh: MeshInstance3D = item.mesh
		geometry.add_mesh(mesh.mesh, mesh.global_transform)
		counts[item.zone] = int(counts.get(item.zone, 0)) + 1
	access.restrict_navigation(geometry, AABB(Vector3(-51, -0.12, -45), Vector3(102, 14, 102)))
	var output := "res://../build/godot_assets/split-activity/"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	if ResourceSaver.save(geometry, output + "navigation-input.res", ResourceSaver.FLAG_COMPRESS) != OK:
		push_error("Cannot save split navigation source geometry")
		quit(1)
		return
	var data := preload("res://nest/spatial/estate_spatial_data.gd").new()
	access.capture_precompiled(data)
	if ResourceSaver.save(data, output + "activity-mask.res", ResourceSaver.FLAG_COMPRESS) != OK:
		push_error("Cannot save split activity mask")
		quit(1)
		return
	var restored := ResourceLoader.load(output + "navigation-input.res", "", ResourceLoader.CACHE_MODE_IGNORE) as NavigationMeshSourceGeometryData3D
	var restored_mask := ResourceLoader.load(output + "activity-mask.res", "", ResourceLoader.CACHE_MODE_IGNORE)
	if restored == null or restored.get_vertices() != geometry.get_vertices() or restored_mask == null or restored_mask.raw_mask != data.raw_mask or restored_mask.connected_mask != data.connected_mask:
		push_error("Split activity export did not preserve its geometry and permissions")
		quit(1)
		return
	var report := {"source": "res://nest/assembly/estate.tscn", "zones": counts, "geometry_sha256": FileAccess.get_sha256(output + "navigation-input.res"), "permissions_sha256": FileAccess.get_sha256("res://nest/assembly/activity_regions.tres"), "physical_obstacles_baked": false, "source_static_bodies": estate.find_children("*", "StaticBody3D", true, false).size(), "source_navigation_links": estate.find_children("*", "NavigationLink3D", true, false).size(), "source_markers": estate.find_children("*", "Marker3D", true, false).size()}
	report["round_trip_verified"] = true
	var file := FileAccess.open(output + "export.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	print("SPLIT_ACTIVITY_EXPORTED ", JSON.stringify(report))
	estate.free()
	access.free()
	quit(0)
