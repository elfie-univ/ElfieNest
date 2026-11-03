extends SceneTree
## Confirm the loaded Godot resource contains the repaired desktop geometry.

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var file := FileAccess.open("res://rooms/estate/ElfieNest-complete-final.glb", FileAccess.READ)
	file.seek(12)
	var length := file.get_32()
	file.get_32()
	var document: Dictionary = JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
	file.close()
	var expected: Dictionary = {}
	var versions: Dictionary = {}
	for node: Dictionary in document.nodes:
		var extras: Dictionary = node.get("extras", {})
		if extras.get("piece") != "worktop" or not str(extras.get("module", "")).begins_with("M"): continue
		var count := 0
		for primitive: Dictionary in document.meshes[int(node.mesh)].primitives:
			count += int(document.accessors[int(primitive.indices)].count)
		expected[str(extras.module) + "/" + str(extras.resident)] = count
		versions[str(extras.module) + "/" + str(extras.resident)] = str(extras.get("exportVersion", ""))
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	await process_frame
	var found := 0
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		var key := str(extras.get("module", "")) + "/" + str(extras.get("resident", ""))
		if extras.get("piece") != "worktop" or not expected.has(key): continue
		if not require(mesh.mesh.get_faces().size() == int(expected[key]), "Imported desktop is stale: " + key): return
		if not require(str(extras.get("exportVersion", "")) == versions[key], "Imported desktop provenance is stale: " + key): return
		found += 1
	if not require(found == 32 and expected.size() == 32, "All 32 desktops must use the repaired source"): return
	print("PASS current desktop geometry imported in all eight rooms: ", found)
	estate.free()
	quit()
