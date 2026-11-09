extends SceneTree
## Confirm the loaded Godot resource contains the repaired desktop geometry.

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	await process_frame
	var found := 0
	var residents := {}
	const SUPPORT = preload("res://test/split_estate_test_support.gd")
	for placement: Node in SUPPORT.placements(estate):
		var prototypes: Dictionary = placement.import_meshes(placement.library.resource_path)
		for index: int in placement.get_child_count():
			var mesh := placement.get_child(index) as MeshInstance3D
			if mesh == null: continue
			var extras: Dictionary = mesh.get_meta("extras", {})
			if extras.get("piece") != "worktop" or not str(extras.get("module", "")).begins_with("M"): continue
			var key := str(extras.module) + "/" + str(extras.resident)
			var original := preload("res://nest/assembly/glb_placement.gd").select_mesh(prototypes, placement.source_nodes[index], str(mesh.get_meta("v044_path", "")), str(extras.module))
			if not require(original != null and mesh.mesh == original and not mesh.mesh.get_faces().is_empty(), "Desktop lost its current GLB geometry: " + key): return
			if not require(not residents.has(key) and not str(extras.get("exportVersion", "")).is_empty(), "Desktop provenance or resident is missing/duplicated: " + key): return
			residents[key] = true
			found += 1
	if not require(found == 32 and residents.size() == 32, "All 32 desktops must use the repaired source"): return
	print("PASS current desktop geometry imported in all eight rooms: ", found)
	estate.free()
	quit()
