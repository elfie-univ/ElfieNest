extends "res://tools/pack_shared_asset_candidate.gd"
## Build organized furniture scenes from the verified native V044 placements.

const FURNITURE := "res://../build/godot-asset-migration/furniture-v044-organized/"
const REVIEW_INPUT := CANDIDATE + "v044-shared-assets.pck"
const PACK_NAME := "v044-furniture-assets.pck"
const REASSEMBLED := "assets/reassembled.scn"
const GLB_PLACEMENT := preload("res://tools/furniture_glb_placement.gd")
const UNSTORED := [
	"owner", "name", "script", "unique_name_in_owner", "scene_file_path", "visible",
	"transform", "position", "basis", "rotation", "rotation_degrees", "quaternion", "scale",
	"global_transform", "global_position", "global_basis", "global_rotation", "global_rotation_degrees",
]
const PLACEMENT_METADATA := ["metadata/v044_path", "metadata/v044_transform", "metadata/v044_visible"]
var saved := {}
var expected := {}
var placement_bindings := {}
var authoring_scenes := {}
var glb_libraries := {}
var authoring_hashes := {}

func scene_location(record: Dictionary) -> String:
	var path: String = record.file
	return path if path.begins_with("previews/") else "assets/" + path

func copy_placement(original: Node, parent: Node3D, source_path: String) -> Node:
	var copy := ClassDB.instantiate(original.get_class()) as Node
	copy.name = "Placement_%04d" % parent.get_child_count()
	for property: Dictionary in original.get_property_list():
		var key := str(property.name)
		if property.usage & PROPERTY_USAGE_STORAGE and key not in UNSTORED:
			copy.set(key, original.get(key))
	if original is Node3D:
		copy.transform = original.global_transform
		copy.visible = original.is_visible_in_tree()
		copy.set_meta("v044_transform", var_to_bytes(original.transform))
		copy.set_meta("v044_visible", original.visible)
	copy.set_meta("v044_path", source_path)
	parent.add_child(copy)
	copy.owner = parent
	return copy

func save_native_scene(pack: PCKPacker, path: String, model: Node3D) -> PackedScene:
	var has_authoring_scene := path.begins_with("assets/furniture/") or path.begins_with("assets/courtyard/")
	var output := FURNITURE + ("native/" if has_authoring_scene else "") + path
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output.get_base_dir()))
	var scene := PackedScene.new()
	if not check(scene.pack(model) == OK and ResourceSaver.save(scene, output, ResourceSaver.FLAG_COMPRESS) == OK,
		"Cannot save organized scene " + output): return null
	if not add_file(pack, BASE + path, output): return null
	var reloaded := ResourceLoader.load(output, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	if not check(reloaded != null, "Cannot read saved scene " + output): return null
	reloaded.take_over_path(BASE + path)
	return reloaded

func authoring_path(file: String) -> String:
	return FURNITURE.path_join("assets").path_join(file)

func glb_reference(path: String) -> PackedScene:
	if not glb_libraries.has(path):
		# The build directory is outside the editor's import root. Cache a typed
		# reference so the binary scene can resolve it during this headless run.
		# The placement reads the actual GLB, including its alternate scenes.
		var reference := PackedScene.new()
		reference.take_over_path(path)
		glb_libraries[path] = reference
	return glb_libraries[path]

func new_glb_placement() -> Node3D:
	return GLB_PLACEMENT.new()

func prepare_authoring_resources(_model: Node3D) -> bool:
	return true

func retain_native_overrides(record: Dictionary) -> bool:
	return record.file.begins_with("courtyard/")

func append_glb_placements(model: Node3D, file: String, placements: Dictionary,
		world: Node3D, aliases: Dictionary, native_overrides: bool) -> bool:
	var binding = new_glb_placement()
	binding.name = file.get_file().get_basename()
	binding.library = glb_reference(authoring_path(file))
	model.add_child(binding)
	binding.owner = model
	var names := PackedStringArray()
	for path: String in placements:
		var original := world.get_node(NodePath(path))
		if original is MultiMeshInstance3D:
			var batch := copy_placement(original, binding, path) as MultiMeshInstance3D
			batch.owner = model
			var source: MultiMesh = original.multimesh
			batch.multimesh = null
			binding.instance_batches[names.size()] = {
				"transform_format": source.transform_format,
				"use_colors": source.use_colors,
				"use_custom_data": source.use_custom_data,
				"instance_count": source.instance_count,
				"visible_instance_count": source.visible_instance_count,
				"custom_aabb": source.custom_aabb,
				"buffer": source.buffer,
			}
			if batch.material_override == null:
				var mesh: Mesh = source.mesh
				if not check(mesh.get_surface_count() == 1, "Expected a single material in V044 batch " + path):
					return false
				batch.material_override = mesh.surface_get_material(0)
			names.append(placements[path].node)
			continue
		var mesh_instance := original as MeshInstance3D
		if not check(mesh_instance != null and mesh_instance.mesh != null, "Missing mesh placement " + path):
			return false
		var part := MeshInstance3D.new()
		part.name = "Placement_%04d" % names.size()
		part.transform = mesh_instance.global_transform
		if aliases.has(path):
			var alias: Dictionary = aliases[path]
			var offset: Array = alias.mesh_translation
			var rotation := Basis(Vector3.UP, -float(alias.mesh_yaw_xz_radians))
			part.transform *= Transform3D(rotation, Vector3(offset[0], offset[1], offset[2]))
		part.visible = mesh_instance.is_visible_in_tree()
		part.layers = mesh_instance.layers
		part.cast_shadow = mesh_instance.cast_shadow
		part.set_meta("v044_path", path)
		if native_overrides:
			part.custom_aabb = mesh_instance.custom_aabb
			part.extra_cull_margin = mesh_instance.extra_cull_margin
			part.material_override = mesh_instance.material_override
			part.material_overlay = mesh_instance.material_overlay
		var materials: Array[Material] = []
		var preserve: bool = placements[path].preserve_material
		var keep_materials := preserve
		for index: int in mesh_instance.mesh.get_surface_count():
			var material := mesh_instance.get_active_material(index)
			var keep := preserve or (native_overrides and material is ShaderMaterial)
			materials.append(material.duplicate() as Material if keep and material != null else null)
			keep_materials = keep_materials or keep
		if keep_materials:
			binding.material_variants[names.size()] = materials
		binding.add_child(part)
		part.owner = model
		names.append(placements[path].node)
	binding.source_nodes = names
	return true

func save_authoring_scene(key: String, record: Dictionary, bindings: Dictionary,
		entries: Dictionary, world: Node3D, aliases: Dictionary) -> bool:
	var model := Node3D.new()
	model.name = str(entries[key].title).validate_node_name()
	var expected_files := {}
	for row: Dictionary in entries[key].parts:
		var path := authoring_path(entries[row.id].file)
		expected_files[ProjectSettings.globalize_path(path).simplify_path()] = true
	var mesh_paths := {}
	for id: String in bindings:
		var file: String = entries[id].file
		if not check(file.ends_with(".glb") and FileAccess.file_exists(authoring_path(file)),
			"Missing furniture GLB " + file):
			model.free()
			return false
		if not append_glb_placements(model, file, bindings[id], world, aliases, retain_native_overrides(record)):
			model.free()
			return false
		for path: String in bindings[id]: mesh_paths[path] = true
	for path: String in record.paths:
		if mesh_paths.has(path): continue
		var original := world.get_node(NodePath(path))
		var has_mesh := (original is MeshInstance3D and original.mesh != null) or (
			original is MultiMeshInstance3D and original.multimesh != null and original.multimesh.mesh != null
		)
		if not check(not has_mesh, "Unbound assembly mesh " + path):
			model.free()
			return false
		copy_placement(original, model, path)
	for child: String in record.children:
		if entries[child].kind == "source": continue
		append_scene(model, authoring_scenes[child])
	var output := authoring_path(record.file)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output.get_base_dir()))
	var packed := PackedScene.new()
	# Binary SCN dependencies use project paths so ResourceLoader can reopen them.
	var saved_ok := prepare_authoring_resources(model) and packed.pack(model) == OK and ResourceSaver.save(packed, output, ResourceSaver.FLAG_COMPRESS) == OK
	model.free()
	if not check(saved_ok, "Cannot save furniture authoring scene " + output): return false
	var dependencies := {}
	for dependency: String in ResourceLoader.get_dependencies(output):
		var file := dependency.get_slice("::", 2) if dependency.contains("::") else dependency
		var path := ProjectSettings.globalize_path(file).simplify_path()
		if path.get_extension() in ["glb", "scn", "tscn"]: dependencies[path] = true
	if not check(dependencies == expected_files, "Furniture file references differ in " + key + ": " + str(dependencies)): return false
	var reloaded := ResourceLoader.load(output, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	if not check(reloaded != null, "Cannot load furniture authoring scene " + output): return false
	var instance := reloaded.instantiate()
	var valid := true
	for child: Node in instance.get_children():
		if child.has_method("bind_meshes") and not child.call("bind_meshes"):
			valid = check(false, "Cannot bind GLB geometry in " + key + " from " + str(child.name))
			break
	instance.free()
	if not valid: return false
	reloaded.take_over_path(output)
	authoring_scenes[key] = reloaded
	authoring_hashes[key] = FileAccess.get_sha256(output)
	return true

func append_scene(model: Node3D, scene: PackedScene) -> void:
	var child: Node3D = scene.instantiate()
	child.name = "Part_" + str(model.get_child_count())
	model.add_child(child)
	child.owner = model

func append_bindings(pack: PCKPacker, key: String, record: Dictionary, world: Node3D,
		model: Node3D, placements: Dictionary) -> bool:
	var bindings: Dictionary = record.get("bindings", {})
	for asset: String in bindings:
		var binding := Node3D.new()
		for path: String in bindings[asset]:
			if not check(not placements.has(path), "Duplicate reference placement " + key + " " + path):
				binding.free()
				return false
			copy_placement(world.get_node(NodePath(path)), binding, path)
			placements[path] = true
		var file := "bindings/" + key.replace(":", "-") + "/" + asset.replace(":", "-") + ".scn"
		var scene := save_native_scene(pack, file, binding)
		binding.free()
		if scene == null: return false
		if not placement_bindings.has(key): placement_bindings[key] = []
		placement_bindings[key].append(scene)
		append_scene(model, scene)
	return true

func save_furniture_scene(pack: PCKPacker, key: String, record: Dictionary, world: Node3D) -> bool:
	var model: Node3D
	var placements := {}
	if not record.groups.is_empty():
		model = row_view(record.groups, world, record.get("front_row", false))
		assign_owners(model, model)
		for index: int in record.groups.size():
			var group: Node = model.get_child(index)
			for part: int in record.groups[index].size():
				group.get_child(part).set_meta("v044_path", record.groups[index][part])
	else:
		model = Node3D.new()
		if not append_bindings(pack, key, record, world, model, placements):
			model.free()
			return false
		for path: String in record.paths:
			if placements.has(path): continue
			var source := world.get_node_or_null(NodePath(path))
			if not check(source != null, "Missing V044 placement " + path):
				model.free()
				return false
			copy_placement(source, model, path)
			placements[path] = true
		for child_id: String in record.children:
			append_scene(model, saved[child_id])
			for path: String in expected[child_id]:
				if not check(not placements.has(path), "Duplicate placement " + key + " " + path):
					model.free()
					return false
				placements[path] = true
	var scene := save_native_scene(pack, scene_location(record), model)
	model.free()
	if scene == null: return false
	saved[key] = scene
	expected[key] = placements
	return true

func same_placement(actual: Node, original: Node) -> bool:
	if actual.get_class() != original.get_class(): return false
	if original is Node3D:
		if actual.visible != original.is_visible_in_tree(): return false
		if not actual.global_transform.is_equal_approx(original.global_transform): return false
		if actual.get_meta("v044_transform") != var_to_bytes(original.transform) or actual.get_meta("v044_visible") != original.visible:
			return false
	for property: Dictionary in original.get_property_list():
		var key := str(property.name)
		if property.usage & PROPERTY_USAGE_STORAGE and key not in UNSTORED:
			if actual.get(key) != original.get(key): return false
	return true

func verify_prototypes(model: Node3D, groups: Array, world: Node3D, key: String) -> bool:
	if not check(model.get_child_count() == groups.size(), "Missing prototype group in " + key): return false
	for index: int in groups.size():
		var group := model.get_child(index) as Node3D
		var paths: Array = groups[index]
		if not check(group.get_child_count() == paths.size(), "Incomplete prototype in " + key): return false
		for part: int in paths.size():
			var path: String = paths[part]
			var mesh := group.get_child(part) as MeshInstance3D
			var original := world.get_node(NodePath(path)) as MeshInstance3D
			if not check(mesh.get_meta("v044_path") == path and mesh.mesh == original.mesh
					and mesh.transform.is_equal_approx(original.global_transform),
				"Prototype geometry differs from V044 in " + key + ": " + path): return false
			for surface: int in mesh.mesh.get_surface_count():
				if not check(mesh.get_active_material(surface) == original.get_active_material(surface),
					"Prototype material differs from V044 in " + key + ": " + path): return false
	return true

func verify_showcase(model: Node3D, key: String) -> bool:
	if not check(model.has_meta("review_front_row"), "Missing front view in " + key): return false
	var boxes: Array[AABB] = []
	for group: Node3D in model.get_children():
		boxes.append(prototype_bounds(group))
	boxes.sort_custom(func(a: AABB, b: AABB) -> bool: return a.position.x < b.position.x)
	var next_x := 0.0
	var last_height := 0.0
	for box: AABB in boxes:
		if not check(absf(box.position.x - next_x) <= 0.0001
				and absf(box.position.y) <= 0.0001 and absf(box.get_center().z) <= 0.0001
				and box.size.y + 0.0001 >= last_height,
			"Prototype row differs from the showcase layout in " + key): return false
		next_x = box.end.x + SHOWCASE_GAP
		last_height = box.size.y
	return true

func verify_furniture_scene(key: String, record: Dictionary, world: Node3D) -> bool:
	var resource_path := BASE + scene_location(record)
	var scene := ResourceLoader.load(resource_path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	if not check(scene != null, "Cannot reload " + key): return false
	var model := scene.instantiate() as Node3D
	root.add_child(model)
	var valid := true
	if not record.groups.is_empty():
		valid = verify_prototypes(model, record.groups, world, key)
		if valid and record.get("front_row", false):
			valid = verify_showcase(model, key)
	else:
		var found := {}
		for node: Node in model.find_children("*", "", true, false):
			if not node.has_meta("v044_path"): continue
			var path := str(node.get_meta("v044_path"))
			if not check(expected[key].has(path) and not found.has(path)
					and same_placement(node, world.get_node(NodePath(path))),
				"V044 placement differs in " + key + ": " + path):
				valid = false
				break
			found[path] = true
		if valid:
			valid = check(found.size() == expected[key].size(), "Incomplete placement set " + key)
		var dependencies := ResourceLoader.get_dependencies(resource_path)
		for child_id: String in record.children:
			var child_path: String = saved[child_id].resource_path
			if not check(dependencies.has(child_path), "Missing scene dependency " + key + ": " + child_path):
				valid = false
		for binding: PackedScene in placement_bindings.get(key, []):
			if not check(dependencies.has(binding.resource_path), "Missing external reference " + key + ": " + binding.resource_path):
				valid = false
	model.free()
	return valid

func assembly_placements(native_plan: Dictionary, instances: Array[Node]) -> Dictionary:
	var placements := {}
	for id: String in native_plan.assembly_roots:
		var instance: Node = saved[id].instantiate()
		instances.append(instance)
		var before := placements.size()
		for node: Node in instance.find_children("*", "", true, false):
			if not node.has_meta("v044_path"): continue
			var path: String = node.get_meta("v044_path")
			if not check(not placements.has(path), "Duplicate assembly placement in world: " + path): return {}
			placements[path] = node
		if id == "view:courtyard-layout" and not check(
				placements.size() - before == native_plan.courtyard_placements,
				"Incomplete courtyard placements"): return {}
	if not check(placements.size() == native_plan.placements, "Incomplete assembly placements"): return {}
	return placements

func copy_world_node(source: Node, normalized: Node, from_assembly: bool) -> Node:
	var copy: Node = ClassDB.instantiate(source.get_class())
	copy.name = normalized.name
	for property: Dictionary in source.get_property_list():
		var key := str(property.name)
		if not property.usage & PROPERTY_USAGE_STORAGE or key in ["owner", "name", "script", "unique_name_in_owner"] or key in PLACEMENT_METADATA:
			continue
		var value: Variant = source.get(key)
		if from_assembly and source is Node3D and key in ["transform", "visible"]: continue
		if not from_assembly and (value is Resource or key.begins_with("surface_material_override/")):
			# The verified part may point to the pre-relocation resource path.
			# Keep the review pack's equivalent canonical resource and overrides.
			value = normalized.get(key)
		copy.set(key, value)
	if from_assembly and source is Node3D:
		# Restore the original local basis after all other stored properties.
		(copy as Node3D).transform = bytes_to_var(source.get_meta("v044_transform"))
		(copy as Node3D).visible = source.get_meta("v044_visible")
	return copy

func reassemble_review_world(native_plan: Dictionary, world: Node3D, frozen_sha: String) -> Dictionary:
	var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(REVIEW.path_join("assembly-report.json")))
	if not check(report.passed and report.frozen_sha256 == frozen_sha, "Missing verified V044 split inputs"): return {}
	var inventory: Array = JSON.parse_string(FileAccess.get_file_as_string(REVIEW.get_base_dir().path_join("full-inventory/static-nodes.json")))
	var reference := (load(BASE + "reference.scn") as PackedScene).instantiate()
	var instances: Array[Node] = [reference]
	var placements := assembly_placements(native_plan, instances)
	if placements.is_empty(): return {}
	var copied := {}
	var loaded_parts := {}
	var used_placements := 0
	for entry: Dictionary in inventory:
		var path: String = entry.path
		var normalized := world.get_node_or_null(NodePath(path))
		if not check(normalized != null and not copied.has(path), "Unknown or repeated V044 node " + path): return {}
		var source: Node = placements.get(path)
		var from_assembly := source != null
		if from_assembly:
			used_placements += 1
		else:
			var id: String = report.node_owners[path]
			if not loaded_parts.has(id):
				var model_file := STAGE.path_join("models/" + id + ".scn")
				if id in report.residual_groups:
					model_file = REVIEW.path_join("parts/" + id + ".scn")
				var part := load(model_file) as PackedScene
				if not check(part != null, "Missing V044 split input " + model_file): return {}
				var instance := part.instantiate()
				instances.append(instance)
				loaded_parts[id] = instance
			source = loaded_parts[id].get_node_or_null(NodePath(path))
			var original := reference.get_node_or_null(NodePath(path))
			if not check(source != null and original != null and signature(source) == signature(original),
				"Split input differs from frozen V044 at " + id + " " + path): return {}
		var copy := copy_world_node(source, normalized, from_assembly)
		if path != ".":
			var parent_path := path.get_base_dir()
			copied["." if parent_path.is_empty() else parent_path].add_child(copy)
		copied[path] = copy
	for instance: Node in instances: instance.free()
	if not check(used_placements == placements.size() and copied.size() == report.source_nodes,
		"Reassembly did not consume every frozen placement"): return {}
	var assembled: Node = copied["."]
	var success := save_scene(assembled, FURNITURE + REASSEMBLED)
	assembled.free()
	if not check(success, "Cannot save rebuilt review world"): return {}
	return {
		"nodes": copied.size(),
		"courtyard_placements": native_plan.courtyard_placements,
		"mesh_nodes": report.mesh_nodes,
		"multimesh_batches": report.multimesh_batches,
		"multimesh_instances": report.multimesh_instances,
		"lights": report.lights,
	}

func verify_reassembled_world(world: Node3D, nodes: int) -> bool:
	var scene := ResourceLoader.load(BASE + "reassembled.scn", "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	if not check(scene != null, "Cannot reload rebuilt review world"): return false
	var rebuilt := scene.instantiate()
	var inventory: Array = JSON.parse_string(FileAccess.get_file_as_string(REVIEW.get_base_dir().path_join("full-inventory/static-nodes.json")))
	var valid := check(rebuilt.find_children("*", "", true, false).size() + 1 == nodes, "Rebuilt node count differs")
	if valid:
		for entry: Dictionary in inventory:
			var path := NodePath(entry.path)
			var actual := rebuilt.get_node_or_null(path)
			var target := world.get_node(path)
			# The root's sibling index belongs to the caller's SceneTree.
			var same_order: bool = entry.path == "." or (actual != null and actual.get_index() == target.get_index())
			if not check(actual != null and same_order and signature(actual) == signature(target),
				"Rebuilt node differs from V044: " + entry.path):
				valid = false
				break
	rebuilt.free()
	return valid

func collect_menu_scenes() -> bool:
	var graph: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FURNITURE + "file-graph.json"))
	for entry: Dictionary in graph.entries.values():
		var path: String = entry.file
		if path.ends_with(".scn") and not path.begins_with("furniture/") and path != "reassembled.scn":
			var source := ProjectSettings.globalize_path(CANDIDATE.path_join("models/" + path.get_file()))
			var destination := ProjectSettings.globalize_path(FURNITURE + "assets/" + path)
			if FileAccess.file_exists(destination): continue
			DirAccess.make_dir_recursive_absolute(destination.get_base_dir())
			if not check(DirAccess.copy_absolute(source, destination) == OK, "Cannot collect menu scene " + path): return false
	return true

func visible_furniture_meshes(viewer: Node) -> Dictionary:
	var meshes := {}
	var model := viewer.get("current") as Node3D
	for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh != null and mesh.is_visible_in_tree() and mesh.layers != 0:
			meshes[mesh.get_meta("v044_path", "")] = mesh
	return meshes

func verify_furniture_selection(viewer: Node, key: String, entry: Dictionary) -> int:
	viewer.call("show_scene", entry.preview, false, entry.get("focus", []))
	var source: bool = entry.kind == "source"
	var rows: Array = entry.get("components" if source else "parts", [])
	var visible := visible_furniture_meshes(viewer)
	var all_paths := {}
	for row: Dictionary in rows:
		var selection := {}
		for path: String in row.paths:
			if not visible.has(path): continue
			selection[path] = true
			all_paths[path] = true
		if not check(not selection.is_empty() and viewer.call("inspect_parts", row.paths, false) == selection.size(),
			"Furniture selection does not cover its full component in " + key + ": " + str(row.get("title", row.get("id")))): return -1
		for path: String in visible:
			var highlighted: bool = visible[path].material_override == viewer.get("inspect_furniture_material")
			if not check(highlighted == selection.has(path), "Wrong highlighted furniture at " + key + ": " + path): return -1
		if source:
			var prototype: Array = row.get("prototypePaths", row.paths)
			var expected_count := 0
			for path: String in prototype:
				if visible.has(path): expected_count += 1
			if not check(expected_count > 0 and viewer.call("inspect_parts", prototype, true) == expected_count,
				"Cannot isolate furniture prototype in " + key + ": " + row.title): return -1
			var isolated := visible_furniture_meshes(viewer)
			if not check(isolated.size() == expected_count and isolated.keys().all(func(path: String) -> bool: return path in prototype),
				"Isolation contains the wrong meshes in " + key + ": " + row.title): return -1
		viewer.call("inspect_parts", [], false)
	if not check(not visible.is_empty() and not visible.has("") and all_paths.size() == visible.size(),
		"Furniture component union is incomplete in " + key): return -1
	return rows.size()

func verify_inspection(controller: Script) -> Dictionary:
	var graph: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FURNITURE + "file-graph.json"))
	var viewer: Node = controller.new()
	root.add_child(viewer)
	var counts := {"files": 0, "selections": 0, "isolations": 0}
	for key: String in graph.entries:
		var entry: Dictionary = graph.entries[key]
		if not entry.file.begins_with("furniture/"): continue
		var count := verify_furniture_selection(viewer, key, entry)
		if count < 0:
			viewer.free()
			return {}
		counts.files += 1
		counts.selections += count
		if entry.kind == "source": counts.isolations += count
	viewer.free()
	return counts

func pack_legacy_previews(pack: PCKPacker, previews: Dictionary) -> bool:
	var pending: Array[String] = []
	for preview: Dictionary in previews.values():
		var path: String = preview.path
		if path.begins_with("models/"): pending.append(BASE + path)
	var packed := {}
	while not pending.is_empty():
		var path: String = pending.pop_back()
		if packed.has(path): continue
		if not add_file(pack, path, CANDIDATE.path_join(path.trim_prefix(BASE))): return false
		packed[path] = true
		for dependency: String in ResourceLoader.get_dependencies(path):
			var file := dependency.get_slice("::", 2) if dependency.contains("::") else dependency
			if file.begins_with(BASE + "models/"): pending.append(file)
	return true

func pack_review_dependencies(pack: PCKPacker, previews: Dictionary) -> bool:
	var verification: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(EXPORTED.path_join("verification-report.json")))
	for path: String in verification.shader_dependencies:
		if not check(FileAccess.get_sha256(path) == verification.shader_dependencies[path], "Shader changed " + path): return false
		if not add_file(pack, path, path): return false
	for name: String in DirAccess.get_files_at(ProjectSettings.globalize_path(STAGE.path_join("resources"))):
		if not add_file(pack, BASE + "resources/" + name, STAGE.path_join("resources/" + name)): return false
	if not pack_legacy_previews(pack, previews): return false
	for path: String in ["project.godot", "review.tscn"]:
		if not add_file(pack, "res://" + path, STAGE.path_join(path)): return false
	for path: String in ["menu.json", "asset-previews.json"]:
		if not add_file(pack, BASE + path, FURNITURE + path): return false
	return (
		add_file(pack, BASE + "reference.scn", STAGE.path_join("reference.scn"))
		and add_file(pack, BASE + "reassembled.scn", FURNITURE + REASSEMBLED)
		and add_file(pack, "res://.godot/global_script_class_cache.cfg", STAGE.path_join("empty-class-cache.cfg"))
		and add_file(pack, "res://review.gd", "res://tools/static_asset_review.gd")
	)

func run() -> void:
	var controller := load("res://tools/static_asset_review.gd") as Script
	if not check(controller != null and controller.can_instantiate(), "Cannot compile review controller"): return
	var native_plan: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FURNITURE + "native-plan.json"))
	var authoring: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FURNITURE + "authoring-bindings.json"))
	var graph: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FURNITURE + "file-graph.json"))
	var previews: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FURNITURE + "asset-previews.json"))
	var aliases := {}
	for alias: Dictionary in native_plan.geometry_aliases.values(): aliases[alias.placement_path] = alias
	var legacy: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CANDIDATE + "review-report.json"))
	if not check(FileAccess.get_sha256(SNAPSHOT) == legacy.frozen_sha256
			and FileAccess.get_sha256(REVIEW_INPUT) == legacy.pack_sha256,
		"V044 review inputs changed"): return
	if not check(ProjectSettings.load_resource_pack(REVIEW_INPUT, false), "Cannot mount V044 review input"): return
	var world := (load(BASE + "reassembled.scn") as PackedScene).instantiate() as Node3D
	root.add_child(world)
	var pack := PCKPacker.new()
	var output := FURNITURE + PACK_NAME
	if not check(not FileAccess.file_exists(output), "Furniture review pack already exists"): return
	if not check(pack.pck_start(output) == OK, "Cannot start furniture review pack"): return
	# Resolve nested scenes before their assemblies.
	var remaining: Array = native_plan.scenes.keys()
	while not remaining.is_empty():
		var progressed := false
		for key: String in remaining.duplicate():
			var record: Dictionary = native_plan.scenes[key]
			if record.children.any(func(id: String) -> bool: return not saved.has(id)): continue
			if not save_furniture_scene(pack, key, record, world): return
			if authoring.has(key) and not save_authoring_scene(key, record, authoring[key], graph.entries, world, aliases): return
			remaining.erase(key)
			progressed = true
		if not check(progressed, "Unresolved furniture scene dependencies"): return
	var assembly := reassemble_review_world(native_plan, world, legacy.frozen_sha256)
	if assembly.is_empty() or not collect_menu_scenes(): return
	if not pack_review_dependencies(pack, previews) or not check(pack.flush() == OK, "Cannot finish furniture review pack"): return
	if not check(ProjectSettings.load_resource_pack(output, true), "Cannot reload furniture review pack"): return
	for key: String in native_plan.scenes:
		if not verify_furniture_scene(key, native_plan.scenes[key], world): return
	if not verify_reassembled_world(world, int(assembly.nodes)): return
	var inspections := verify_inspection(controller)
	if inspections.is_empty(): return
	var menu: Array = JSON.parse_string(FileAccess.get_file_as_string(FURNITURE + "menu.json"))
	for key: String in menu:
		var path := BASE + str(previews[key].path)
		if not check(ResourceLoader.exists(path, "PackedScene"), "Missing menu preview " + key): return
	var viewer: Node = controller.new()
	root.add_child(viewer)
	var courtyard_count := 0
	for key: String in graph.entries:
		var entry: Dictionary = graph.entries[key]
		if not entry.file.begins_with("courtyard/"): continue
		if not check(viewer.call("show_scene", key, false, entry.get("focus", [])) > 0, "Empty courtyard preview " + key):
			viewer.free()
			return
		if not entry.has("owner"): courtyard_count += 1
	viewer.free()
	store_json(FURNITURE + "review-report.json", {
		"passed": true,
		"assets": menu.size(),
		"furniture_assets": 48,
		"scenes": saved.size(),
		"placements": native_plan.placements,
		"reassembly": assembly,
		"furniture_inspection": inspections,
		"courtyard_previews": courtyard_count,
		"geometry_aliases": native_plan.geometry_aliases.size(),
		"glb_assemblies": authoring_hashes,
		"frozen_sha256": legacy.frozen_sha256,
		"pack_sha256": FileAccess.get_sha256(output),
	})
	print("FURNITURE_NATIVE_PASS menus=", menu.size(), " scenes=", saved.size(), " placements=", native_plan.placements,
		" reassembled_nodes=", assembly.nodes)
	world.free()
	quit(0)
