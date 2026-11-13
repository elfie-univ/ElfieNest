extends SceneTree
## Forest edits keep one terrain source and restore shared stones in assembly.

const GROUND := "res://nest/courtyard/overview/courtyard-all/courtyard-layout.scn"
const BINDING := preload("res://nest/assembly/glb_placement.gd")

func _initialize() -> void:
	call_deferred("run")

static func validate_definition(scene: Node3D) -> String:
	for stone: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		if stone.has_meta("landscape_stone_index") and stone.mesh != null:
			return "The ground scene embeds a second copy of shared stone geometry"
	return ""

static func validate_scene(scene: Node3D) -> String:
	var stones := {}
	var shared_meshes := {}
	var found_terrain := false
	for binding: Node in scene.find_children("*", "Node3D", true, false):
		if binding.get_script() != BINDING:
			continue
		if binding.source_nodes.size() != binding.get_child_count():
			return "A GLB binding has lost its placement correspondence"
		for child: Node in binding.get_children():
			if not child is MeshInstance3D:
				continue
			if child.mesh == null:
				return "An assembled source has no imported mesh"
			if child.has_meta("landscape_stone_index"):
				if not binding.library.resource_path.ends_with("/shared/shore-stones.glb"):
					return "A landscape stone is not owned by the shared library"
				stones[int(child.get_meta("landscape_stone_index"))] = true
				shared_meshes[child.mesh.get_instance_id()] = true
				if str(child.get_meta("stone_family", "")) not in ["block", "slab", "cut"]:
					return "A landscape stone has lost its shape family"
			var source_path := str(child.get_meta("v044_path", ""))
			if source_path.ends_with("CY R003 finish LANDSCAPE grouped stones"):
				return "The old ground-owned stone group is still assembled"
			if source_path.ends_with("COMPLETE Building garden island"):
				found_terrain = true
	if not found_terrain:
		return "The formal terrain source is missing"
	if stones.size() != 66:
		return "Expected 66 restored landscape stones, got %d" % stones.size()
	for index: int in 66:
		if not stones.has(index):
			return "A landscape stone placement is missing"
	if shared_meshes.size() >= 40:
		return "Landscape stones still store one independent mesh per placement"
	return ""

func run() -> void:
	var scene := (load(GROUND) as PackedScene).instantiate() as Node3D
	var definition_error := validate_definition(scene)
	if not definition_error.is_empty():
		scene.free()
		push_error(definition_error)
		quit(1)
		return
	root.add_child(scene)
	await process_frame
	var error := validate_scene(scene)
	scene.free()
	if not error.is_empty():
		push_error(error)
		quit(1)
		return
	print("FOREST_STONE_OWNERSHIP_OK")
	quit(0)
