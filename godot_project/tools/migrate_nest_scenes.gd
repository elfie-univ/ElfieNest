extends "res://tools/pack_furniture_review.gd"
## One-time migration of the verified placements to formal imported resources.

const FORMAL_PLACEMENT := preload("res://nest/assembly/glb_placement.gd")
const NEST := "res://nest/"
const SEED := "res://../build/godot-asset-migration/nest-source-seed.json"
const INDEX := NEST + "assembly/asset-index.json"

var visited := {}

func authoring_path(file: String) -> String:
	return NEST + file

func new_glb_placement() -> Node3D:
	return FORMAL_PLACEMENT.new()

func glb_reference(path: String) -> PackedScene:
	return load(path) as PackedScene

func retain_native_overrides(_record: Dictionary) -> bool:
	return true

func localize_review_resource(value: Variant) -> bool:
	if value is Dictionary or value is Array:
		var items: Array = value.values() if value is Dictionary else value
		for item: Variant in items:
			if not localize_review_resource(item): return false
		return true
	if not value is Resource or value is PackedScene or value is Script:
		return true
	var identity: int = value.get_instance_id()
	if visited.has(identity): return true
	visited[identity] = true
	for property: Dictionary in value.get_property_list():
		if property.usage & PROPERTY_USAGE_STORAGE and str(property.name) != "resource_path":
			if not localize_review_resource(value.get(property.name)): return false
	var path: String = value.resource_path
	if not path.begins_with(BASE): return true
	if not check(not value is ArrayMesh, "Unexpected baked mesh in a formal scene: " + path):
		return false
	if value is Texture:
		var output := NEST + "assembly/render-resources/" + path.get_file()
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output.get_base_dir()))
		if not check(ResourceSaver.save(value, output, ResourceSaver.FLAG_COMPRESS) == OK, "Cannot save render resource " + output):
			return false
		value.take_over_path(output)
	else:
		value.resource_path = ""
	return true

func prepare_authoring_resources(model: Node3D) -> bool:
	for node: Node in model.find_children("*", "", true, false):
		for property: Dictionary in node.get_property_list():
			if property.usage & PROPERTY_USAGE_STORAGE and str(property.name) != "owner":
				if not localize_review_resource(node.get(property.name)): return false
	return true

func run() -> void:
	var seed: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(SEED))
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(INDEX))
	var entries: Dictionary = index.fileGraph.entries
	for record: Dictionary in seed.scenes.values():
		if not check(not FileAccess.file_exists(authoring_path(record.file)), "Formal scene already exists: " + str(record.file)):
			return
	if not check(ProjectSettings.load_resource_pack(REVIEW_INPUT, false), "Missing audited V044 migration input"):
		return
	var world := (load(BASE + "reassembled.scn") as PackedScene).instantiate() as Node3D
	root.add_child(world)
	var aliases := {}
	for alias: Dictionary in seed.aliases.values():
		aliases[alias.placement_path] = alias
	var remaining: Array = seed.scenes.keys()
	while not remaining.is_empty():
		var progressed := false
		for key: String in remaining.duplicate():
			var record: Dictionary = seed.scenes[key]
			if record.children.any(func(id: String) -> bool: return entries[id].kind != "source" and not authoring_scenes.has(id)):
				continue
			if not save_authoring_scene(key, record, seed.bindings[key], entries, world, aliases):
				return
			remaining.erase(key)
			progressed = true
		if not check(progressed, "Unresolved formal scene dependencies: " + str(remaining)): return
	world.free()
	var model := (load(authoring_path(entries["view:estate-layout"].file)) as PackedScene).instantiate()
	root.add_child(model)
	var meshes := {}
	for node: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		if node.mesh == null: continue
		var path: String = node.get_meta("v044_path")
		if not check(not meshes.has(path), "Duplicate formal mesh placement " + path): return
		meshes[path] = true
	if not check(meshes.size() == int(seed.visible_nodes), "Formal mesh inventory differs: " + str(meshes.size())):
		return
	var batches := 0
	for node: MultiMeshInstance3D in model.find_children("*", "MultiMeshInstance3D", true, false):
		if not check(node.multimesh != null and node.multimesh.mesh != null, "Unbound formal batch " + str(node.name)):
			return
		batches += 1
	print("NEST_FORMAL_SCENES=", authoring_scenes.size(), " meshes=", meshes.size(), " batches=", batches)
	model.free()
	quit(0)
