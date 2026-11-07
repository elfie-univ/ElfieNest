extends "res://../build/godot-asset-migration/evaluated-v044/capture.gd"
## Authoring interchange only. Runtime fidelity is verified separately in native scenes.

const SNAPSHOT := "res://../build/godot-asset-migration/evaluated-v044/v044-evaluated-static.scn"
const BINDINGS := "res://../build/godot-asset-migration/static-export-bindings.json"
const DESTINATION := "res://../build/godot-asset-migration/exported-v044-native/authoring"
var converted_meshes := {}
var converted_materials := {}
var native_only_materials := {}

func authored_material(source: Material) -> Material:
	if source == null: return null
	var identity: int = source.get_instance_id()
	if converted_materials.has(identity): return converted_materials[identity]
	var original := source
	if source is ShaderMaterial:
		source = source.get_meta("source_material", null) as Material
		if source == null:
			# Shader programs and their parameters remain authoritative in native resources.
			# The exchange mesh deliberately has no invented replacement material.
			native_only_materials[str(identity)] = original.resource_path
			converted_materials[identity] = null
			return null
	var result := source.duplicate() as Material
	result.resource_path = ""
	for key: StringName in result.get_meta_list():
		if result.get_meta(key) is Object: result.remove_meta(key)
	converted_materials[identity] = result
	return result

func authored_mesh(source: MeshInstance3D) -> Mesh:
	var material_ids: Array = []
	for index in source.mesh.get_surface_count():
		var material := source.get_active_material(index)
		material_ids.append(material.get_instance_id() if material != null else 0)
	var key := str([source.mesh.get_instance_id(), material_ids])
	if converted_meshes.has(key): return converted_meshes[key]
	var result := source.mesh.duplicate() as Mesh
	result.resource_path = ""
	for index in result.get_surface_count():
		result.surface_set_material(index, authored_material(source.get_active_material(index)))
	for meta: StringName in result.get_meta_list():
		if result.get_meta(meta) is Object: result.remove_meta(meta)
	converted_meshes[key] = result
	return result

func run() -> void:
	var started := Time.get_ticks_msec()
	var plans: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(BINDINGS))
	if not check(FileAccess.get_sha256(SNAPSHOT) == plans.snapshot_sha256, "Frozen source changed"): return
	var native_report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(DESTINATION.get_base_dir().path_join("export-report.json")))
	if not check(native_report.get("passed", false), "Native preservation must pass first"): return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(DESTINATION))
	var world := (load(SNAPSHOT) as PackedScene).instantiate()
	root.add_child(world)
	var selections: Array = []
	var covered := {}
	for item: Dictionary in plans.items:
		if item.category == "layouts" or item.id.ends_with("-layout") or item.id.ends_with("-planting"): continue
		selections.append(item)
		for path: String in item.paths: covered[path] = true
	var variants: Array = []
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		var path := str(world.get_path_to(node))
		if not covered.has(path): variants.append(path)
	if not variants.is_empty():
		selections.append({"id": "retained-placement-variants", "paths": variants, "menu": [], "category": "internal"})
	var records: Array = []
	for item: Dictionary in selections:
		var model := Node3D.new()
		model.name = item.id.replace("-", "_")
		root.add_child(model)
		var source_paths: Array = []
		for path: String in item.paths:
			var original := world.get_node(NodePath(path)) as MeshInstance3D
			if original == null or original.mesh == null: continue
			var copy := MeshInstance3D.new()
			copy.name = "part_%05d" % source_paths.size()
			copy.mesh = authored_mesh(original)
			copy.transform = original.global_transform
			copy.set_meta("extras", {"v044_path": path, "source_name": str(original.name), "provenance": "Frozen evaluated V044; reconstructed authoring exchange, not a historical Blender original"})
			model.add_child(copy)
			source_paths.append(path)
		if source_paths.is_empty():
			model.free()
			continue
		var document := GLTFDocument.new()
		document.image_format = "PNG"
		var state := GLTFState.new()
		if not check(document.append_from_scene(model, state) == OK, "GLB conversion failed: " + item.id): return
		var output := DESTINATION.path_join(item.id + ".glb")
		if not check(document.write_to_filesystem(state, ProjectSettings.globalize_path(output)) == OK, "GLB save failed: " + item.id): return
		records.append({"id": item.id, "menu": item.menu, "glb": output, "source_paths": source_paths, "mesh_nodes": source_paths.size(), "sha256": FileAccess.get_sha256(output)})
		model.free()
		print("EXPORTED_AUTHORING_ASSET ", item.id, " meshes=", source_paths.size())
	var report := {"snapshot_sha256": plans.snapshot_sha256, "items": records, "native_only_materials": native_only_materials, "elapsed_ms": Time.get_ticks_msec() - started, "scope": "Editable geometry interchange reconstructed from evaluated V044. Shader effects, native instance batches, lights, collision and runtime animation remain in native companions. No GLB roundtrip or Blender render equivalence claim."}
	var file := FileAccess.open(DESTINATION.path_join("authoring-report.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	print("AUTHORING_EXPORT_RESULT ", JSON.stringify({"glbs": records.size(), "native_only_materials": native_only_materials.size(), "elapsed_ms": report.elapsed_ms}))
	world.free()
	quit(0)
