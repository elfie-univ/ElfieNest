extends "res://tools/export_static_assets.gd"
## Assemble the review world from split node payloads, never from a whole-world instance.

const REVIEW := "res://../build/godot-asset-migration/asset-review"
const EXPORTED := "res://../build/godot-asset-migration/exported-v044-native"
var order: Array = []
var payloads: Dictionary = {}
var instances: Array[Node] = []

func residual_id(entry: Dictionary) -> String:
	var extras: Dictionary = entry.extras
	if extras.get("exportLayer") == "layout:pod":
		return "bedroom-placement-" + str(extras.get("module", "unknown")).to_lower()
	return "scene-support"

func load_parts(parts: Array, owners: Dictionary) -> bool:
	for part: Dictionary in parts:
		var scene := ResourceLoader.load(part.file, "PackedScene") as PackedScene
		if not check(scene != null, "Cannot load " + part.file): return false
		var instance := scene.instantiate()
		instances.append(instance)
		for path: String in part.paths:
			var node := instance.get_node_or_null(NodePath(path))
			if not check(node != null, "Missing asset node: " + part.id + " " + path): return false
			if owners[path] == part.id: payloads[path] = node
	return true

func save_scene(node: Node, path: String) -> bool:
	var scene := PackedScene.new()
	assign_owners(node, node)
	return check(scene.pack(node) == OK and ResourceSaver.save(scene, path, ResourceSaver.FLAG_COMPRESS) == OK, "Cannot save " + path)

func run() -> void:
	var started := Time.get_ticks_msec()
	var bindings: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(BINDINGS))
	if not check(FileAccess.get_sha256(SNAPSHOT) == bindings.snapshot_sha256, "Frozen V044 changed"): return
	var exported: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(EXPORTED.path_join("export-report.json")))
	if not check(exported.passed and exported.snapshot_sha256 == bindings.snapshot_sha256, "Invalid split export"): return
	order = JSON.parse_string(FileAccess.get_file_as_string(REVIEW.get_base_dir().path_join("full-inventory/static-nodes.json")))
	var owners := {}
	var sizes := {}
	var parts: Array = []
	for item: Dictionary in bindings.items:
		var file := EXPORTED.path_join("models/" + item.id + ".scn")
		parts.append({"id": item.id, "file": file, "paths": item.paths})
		for path: String in item.paths:
			if not owners.has(path) or item.paths.size() < sizes[path]:
				owners[path] = item.id
				sizes[path] = item.paths.size()
	var residual := {}
	for entry: Dictionary in order:
		if owners.has(entry.path): continue
		var id := residual_id(entry)
		owners[entry.path] = id
		if not residual.has(id): residual[id] = []
		residual[id].append(entry.path)
	if not check(owners.size() == order.size(), "Inventory contains duplicate or unknown paths"): return
	var reference := (load(EXPORTED.path_join("v044-static-world.scn")) as PackedScene).instantiate()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(REVIEW.path_join("parts")))
	for id: String in residual:
		var required := {".": true}
		var selected := {}
		for path: String in residual[id]:
			selected[path] = true
			var ancestor := path
			while ancestor != "" and ancestor != ".":
				required[ancestor] = true
				ancestor = ancestor.get_base_dir()
		var piece := clone_selected(reference, reference, required, selected)
		var file := REVIEW.path_join("parts/" + id + ".scn")
		if not save_scene(piece, file): return
		piece.free()
		parts.append({"id": id, "file": file, "paths": residual[id]})
	if not load_parts(parts, owners): return
	var placed := {}
	for entry: Dictionary in order:
		var path: String = entry.path
		var original := reference.get_node_or_null(NodePath(path))
		var component := payloads.get(path) as Node
		if not check(component != null and original != null and signature(component) == signature(original), "Node payload differs: " + path): return
		var copy: Node = ClassDB.instantiate(component.get_class())
		copy.name = component.name
		for p: Dictionary in component.get_property_list():
			if p.usage & PROPERTY_USAGE_STORAGE and str(p.name) not in ["owner", "name", "script", "unique_name_in_owner"]:
				copy.set(p.name, component.get(p.name))
		if path != ".":
			var parent_path := path.get_base_dir()
			(placed["." if parent_path.is_empty() else parent_path] as Node).add_child(copy)
		placed[path] = copy
	for instance: Node in instances: instance.free()
	var world := placed["."] as Node
	var output := REVIEW.path_join("reassembled.scn")
	if not save_scene(world, output): return
	world.free()
	var reloaded := (ResourceLoader.load(output, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene).instantiate()
	var original_report := inspect(reference)
	var after := inspect(reloaded)
	var frozen: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OUT.path_join("after.json")))
	if not check(after.nodes == frozen.nodes and after.sharing == frozen.sharing, "Reassembly differs from frozen V044" ): return
	if not check(after == original_report, "Reassembly differs from exported V044 reference"): return
	for entry: Dictionary in order:
		var path: String = entry.path
		var a := reloaded.get_node(NodePath(path))
		var b := reference.get_node(NodePath(path))
		if not check(signature(a) == signature(b) and a.get_index() == b.get_index(), "Reload changed payload or order: " + path): return
	var counts := {}
	for id: String in owners.values(): counts[id] = counts.get(id, 0) + 1
	store_json(REVIEW.path_join("assembly-report.json"), {"passed": true, "asset_views": bindings.items.size(), "source_nodes": order.size(), "placed_nodes": placed.size(), "mesh_nodes": after.mesh_nodes, "multimesh_batches": after.multimesh_batches, "multimesh_instances": after.multimesh_instances, "lights": after.lights, "sharing_preserved": true, "frozen_sha256": bindings.snapshot_sha256, "assembly_sha256": FileAccess.get_sha256(output), "node_owners": owners, "component_node_counts": counts, "residual_groups": residual.keys(), "scope": "Frozen V044 static review. No runtime animation or navigation equivalence claim.", "elapsed_ms": Time.get_ticks_msec() - started})
	print("REASSEMBLY_PASS nodes=", placed.size(), " asset_views=", bindings.items.size())
	reloaded.free()
	reference.free()
	quit(0)
