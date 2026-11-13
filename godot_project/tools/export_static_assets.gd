extends "res://../build/godot-asset-migration/evaluated-v044/capture.gd"
## Lossless native static export. No GLB conversion or behavior reconstruction.

const SNAPSHOT := "res://../build/godot-asset-migration/evaluated-v044/v044-evaluated-static.scn"
const BINDINGS := "res://../build/godot-asset-migration/static-export-bindings.json"
var destination := "res://../build/godot-asset-migration/exported-v044-native"
var resources_saved := {}
var visiting := {}
var dependencies := {}
var source_by_path := {}
var signatures := {}
var export_errors: Array[String] = []
var resource_count := 0

func fail(message: String) -> void:
	export_errors.append(message)
	push_error(message)

func externalize(value: Variant) -> void:
	if value is Resource:
		# ImageTexture serializes its Image inline. Giving that Image an external
		# path makes the binary texture loader read an invalid resource-table index.
		if value is Image: return
		var identity: int = value.get_instance_id()
		if resources_saved.has(identity): return
		if value is Shader or value is Script:
			if not value.resource_path.is_empty() and not value.resource_path.contains("::"):
				dependencies[value.resource_path] = FileAccess.get_sha256(value.resource_path)
				return
		if visiting.has(identity):
			fail("Cyclic resource graph requires explicit export binding: " + value.get_class())
			return
		visiting[identity] = true
		value.resource_path = ""
		for property: Dictionary in value.get_property_list():
			if property.usage & PROPERTY_USAGE_STORAGE and str(property.name) not in ["resource_path", "resource_scene_unique_id"]:
				externalize(value.get(property.name))
		visiting.erase(identity)
		if not export_errors.is_empty(): return
		var path := destination.path_join("resources/r%05d.res" % resource_count)
		resource_count += 1
		if ResourceSaver.save(value, path, ResourceSaver.FLAG_COMPRESS) != OK:
			fail("Resource save failed: " + path)
			return
		value.take_over_path(path)
		resources_saved[identity] = path
	elif value is Array:
		for item: Variant in value: externalize(item)
	elif value is Dictionary:
		for item: Variant in value.values(): externalize(item)

func visit(node: Node, world: Node) -> void:
	var path := str(world.get_path_to(node))
	source_by_path[path] = node
	for property: Dictionary in node.get_property_list():
		if property.usage & PROPERTY_USAGE_STORAGE and str(property.name) not in ["owner", "script"]:
			externalize(node.get(property.name))
	for child in node.get_children(): visit(child, world)

func signature(node: Node) -> String:
	var properties := {}
	for p: Dictionary in node.get_property_list():
		var key := str(p.name)
		if p.usage & PROPERTY_USAGE_STORAGE and key not in ["owner", "script"]:
			var value: Variant = node.get(p.name)
			properties[key] = digest(value) if value is Resource else value
	return digest([node.get_class(), properties])

func remember(node: Node, world: Node) -> void:
	signatures[str(world.get_path_to(node))] = signature(node)
	for child in node.get_children(): remember(child, world)

func clone_selected(source: Node, world: Node, required: Dictionary, selected: Dictionary, owner_root: Node = null) -> Node:
	var path := str(world.get_path_to(source))
	if not required.has(path): return null
	var copy: Node = ClassDB.instantiate(source.get_class())
	copy.name = source.name
	for p: Dictionary in source.get_property_list():
		var key := str(p.name)
		if p.usage & PROPERTY_USAGE_STORAGE and key not in ["owner", "script", "name", "unique_name_in_owner"]:
			copy.set(p.name, source.get(p.name))
	# Ancestors retain transforms and visibility, but do not add unselected geometry.
	if copy is MeshInstance3D and not selected.has(path):
		copy.mesh = null
		copy.material_override = null
		copy.material_overlay = null
	if owner_root == null: owner_root = copy
	for child in source.get_children():
		var result := clone_selected(child, world, required, selected, owner_root)
		if result != null:
			copy.add_child(result)
	return copy

func assign_owners(node: Node, owner_root: Node) -> void:
	if node != owner_root: node.owner = owner_root
	for child: Node in node.get_children(): assign_owners(child, owner_root)

func verify_selected(copy: Node, selected: Dictionary) -> Array[String]:
	var failures: Array[String] = []
	for path: String in selected:
		var node := copy.get_node_or_null(NodePath(path))
		if node == null or signature(node) != signatures[path]:
			failures.append(path)
	return failures

func store_json(path: String, data: Variant) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(data, "  "))
	file.close()

func run() -> void:
	var started := Time.get_ticks_msec()
	var override := OS.get_environment("ELFIENEST_STATIC_EXPORT_DEST")
	if not override.is_empty(): destination = override
	var plans: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(BINDINGS))
	if not check(plans.unbound_items.is_empty(), "Unbound menu entries: " + str(plans.unbound_items)): return
	if not check(FileAccess.get_sha256(SNAPSHOT) == plans.snapshot_sha256, "Frozen snapshot fingerprint mismatch"): return
	for folder in ["resources", "models", "assets"]:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(destination.path_join(folder)))
	var world := (load(SNAPSHOT) as PackedScene).instantiate()
	root.add_child(world)
	var before := inspect(world)
	var frozen: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://../build/godot-asset-migration/evaluated-v044/after.json"))
	if not check(before.nodes == frozen.nodes, "Snapshot does not reproduce its frozen fingerprints"): return
	remember(world, world)
	visit(world, world)
	if not check(export_errors.is_empty(), str(export_errors)): return
	resource_hashes.clear()
	var records: Array = []
	for item: Dictionary in plans.items:
		var selected := {}
		var required := {".": true}
		for path: String in item.paths:
			if not source_by_path.has(path):
				fail("Unknown frozen path: " + path)
				continue
			selected[path] = true
			var ancestor := path
			required[ancestor] = true
			while ancestor.contains("/"):
				ancestor = ancestor.get_base_dir()
				required[ancestor] = true
		if not check(export_errors.is_empty(), str(export_errors)): return
		var copy := clone_selected(world, world, required, selected)
		root.add_child(copy)
		assign_owners(copy, copy)
		var packed := PackedScene.new()
		if not check(packed.pack(copy) == OK, "Asset scene packing failed: " + item.id): return
		var model_path := destination.path_join("models/" + item.id + ".scn")
		if not check(ResourceSaver.save(packed, model_path, ResourceSaver.FLAG_COMPRESS) == OK, "Asset scene saving failed: " + item.id): return
		copy.free()
		packed = null
		var reloaded := (ResourceLoader.load(model_path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene).instantiate()
		root.add_child(reloaded)
		var failures := verify_selected(reloaded, selected)
		if not check(failures.is_empty(), "Reload changed asset " + item.id + ": " + str(failures.slice(0, 8))): return
		var wrapper_path := destination.path_join("assets/" + item.id + ".tscn")
		var wrapper := FileAccess.open(wrapper_path, FileAccess.WRITE)
		wrapper.store_string('[gd_scene load_steps=2 format=3]\n[ext_resource type="PackedScene" path="' + model_path + '" id="1"]\n[node name="Asset" instance=ExtResource("1")]\n')
		wrapper.close()
		records.append({"id": item.id, "menu": item.menu, "model": model_path, "scene": wrapper_path, "checked_nodes": selected.size(), "source_binding": item.binding, "sha256": FileAccess.get_sha256(model_path), "failures": failures})
		reloaded.free()
		print("EXPORTED_STATIC_ASSET ", item.id, " nodes=", selected.size())
	var packed_world := PackedScene.new()
	if not check(packed_world.pack(world) == OK, "Full static world packing failed"): return
	var world_path := destination.path_join("v044-static-world.scn")
	if not check(ResourceSaver.save(packed_world, world_path, ResourceSaver.FLAG_COMPRESS) == OK, "Full static world saving failed"): return
	world.free()
	packed_world = null
	resource_hashes.clear()
	var rebuilt := (ResourceLoader.load(world_path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene).instantiate()
	root.add_child(rebuilt)
	var after := inspect(rebuilt)
	var changes: Array = []
	for path: String in before.nodes:
		if before.nodes[path] != after.nodes.get(path): changes.append(path)
	for path: String in after.nodes:
		if not before.nodes.has(path): changes.append(path)
	var report := {"snapshot_sha256": plans.snapshot_sha256, "catalog_sha256": plans.catalog_sha256, "destination": destination, "items": records, "assets_exported": records.size(), "resources_saved": resource_count, "source_nodes": before.nodes.size(), "output_nodes": after.nodes.size(), "mesh_nodes": after.mesh_nodes, "multimesh_batches": after.multimesh_batches, "multimesh_instances": after.multimesh_instances, "lights": after.lights, "full_world_changed_nodes": changes, "sharing_preserved": before.sharing == after.sharing, "dependencies": dependencies, "elapsed_ms": Time.get_ticks_msec() - started, "scope": "Native static asset extraction from the frozen V044 scene. Source-scoped asset views preserve original hierarchy and native batch boundaries; not a GLB/BLEND authoring conversion or dynamic production-world migration."}
	report["passed"] = records.size() == plans.items.size() and changes.is_empty() and before.sharing == after.sharing and export_errors.is_empty()
	store_json(destination.path_join("export-report.json"), report)
	rebuilt.free()
	print("STATIC_EXPORT_RESULT ", JSON.stringify({"passed": report.passed, "assets": records.size(), "resources": resource_count, "changed": changes.size(), "elapsed_ms": report.elapsed_ms}))
	quit(0 if report.passed else 1)
