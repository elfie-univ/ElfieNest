extends SceneTree
## Build the existing Nest Lab review from formal Nest source files.

const NEST := "res://nest/"
const INDEX := NEST + "assembly/asset-index.json"
const BASE := "res://v044-review/"
const OUTPUT := "res://../build/godot-asset-migration/nest-web/"
const CONTROLLER_PATH := "res://tools/static_asset_review.gd"
const CONTROLLER := preload("res://tools/static_asset_review.gd")
const SHELL := """config_version=5

[application]
run/main_scene="res://review.tscn"

[display]
window/size/viewport_width=1280
window/size/viewport_height=800

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
"""
const REVIEW_SCENE := """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://review.gd" id="1"]

[node name="AssetReview" type="Node3D"]
script = ExtResource("1")
"""

var pack := PCKPacker.new()
var packed: Dictionary = {}
var source_hashes: Dictionary = {}

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func write(path: String, content: String) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if not require(file != null, "Cannot write " + path): return false
	file.store_string(content)
	file.close()
	return true

func add_file(target: String, source: String) -> bool:
	if packed.has(target): return true
	if not require(pack.add_file(target, source) == OK, "Cannot pack " + source): return false
	packed[target] = true
	return true

func add_generated(target: String, content: String) -> bool:
	var source := OUTPUT + target.get_file()
	return write(source, content) and add_file(target, source)

func dependencies(source: String) -> PackedStringArray:
	var files := PackedStringArray()
	for dependency: String in ResourceLoader.get_dependencies(source):
		files.append(dependency.get_slice("::", 2) if dependency.contains("::") else dependency)
	if source.get_extension() in ["gdshader", "gdshaderinc"]:
		for line: String in FileAccess.get_file_as_string(source).split("\n"):
			if not line.strip_edges().begins_with("#include "): continue
			var include := line.get_slice('"', 1)
			files.append(include if include.begins_with("res://") else source.get_base_dir().path_join(include))
	return files

func add_resource(path: String) -> bool:
	path = path.simplify_path()
	if packed.has(path) or packed.has(path + ".import"): return true
	if not require(path.begins_with("res://") and not path.begins_with("res://../")
			and not path.begins_with(BASE), "Dependency outside the Godot source project: " + path):
		return false
	var imported := path + ".import"
	if FileAccess.file_exists(imported):
		var config := ConfigFile.new()
		if not require(config.load(imported) == OK, "Cannot read import options " + imported): return false
		var destination: String = config.get_value("remap", "path", config.get_value("remap", "path.s3tc", ""))
		if not require(destination.begins_with("res://.godot/imported/"), "Missing Web-compatible import: " + path):
			return false
		var checksum := destination.get_basename().trim_suffix(".s3tc") + ".md5"
		var cached := ConfigFile.new()
		if not require(cached.load(checksum) == OK and cached.get_value("", "source_md5", "") == FileAccess.get_md5(path),
				"Stale Godot import for " + path + ". Refresh the Godot Web build first."):
			return false
		var metadata := OUTPUT + path.sha256_text() + ".import"
		config.set_value("remap", "path", destination)
		if not require(config.save(metadata) == OK, "Cannot package import options " + path): return false
		if not add_file(imported, metadata) or not add_file(destination, destination): return false
	else:
		if not add_file(path, path): return false
	if not path.begins_with("res://.godot/"):
		source_hashes[path] = FileAccess.get_sha256(path)
	for file: String in dependencies(path):
		if not add_resource(file): return false
	return true

func verify_scene_links(path: String, entry: Dictionary, entries: Dictionary) -> bool:
	var expected := {}
	for part: Dictionary in entry.get("parts", []):
		expected[NEST + str(entries[part.id].file)] = true
	var actual := {}
	for dependency: String in dependencies(path):
		if dependency.get_extension() in ["glb", "scn", "tscn"]:
			actual[dependency.simplify_path()] = true
	return require(actual == expected, "Scene references differ from the asset index: " + path)

func pack_reference() -> bool:
	# Evaluate the retained merged source through its normal rendering inputs.
	var world := (load(NEST + "nest.tscn") as PackedScene).instantiate() as Node3D
	world.set_script(null)
	world.get_node("ObservationHUD").free()
	root.add_child(world)
	var generated := Node3D.new()
	generated.name = "Generated"
	world.add_child(generated)
	var estate := (load(NEST + "estate/estate.tscn") as PackedScene).instantiate() as Node3D
	estate.name = "CompleteEstate"
	generated.add_child(estate)
	if not require(estate.restore_error.is_empty(), "Cannot restore the merged estate instances"): return false
	var physics := (load(NEST + "estate/estate_physics.gd") as Script).new() as Node3D
	physics.name = "EstatePhysics"
	generated.add_child(physics)
	physics.build(estate, true)
	if not require(physics.outdoor_access != null, "Cannot restore merged outdoor access"): return false
	var optics: RefCounted = (load(NEST + "estate/estate_lighting_sample.gd") as Script).new()
	optics.bind_m01(world)
	optics.apply_environment(1.0, false, true, false, PackedStringArray(), true)
	var water := (load(NEST + "estate/estate_water_display.gd") as Script).new() as Node3D
	water.name = "ObserverFountainLighting"
	generated.add_child(water)
	water.bind(estate, world.get_node("WorldEnvironment").environment, false)
	water.sample(0.0, false)
	water.set_presentation_paused(true)
	make_static(world, world, {})
	var reference := PackedScene.new()
	var file := OUTPUT + "reference.scn"
	var saved := reference.pack(world) == OK and ResourceSaver.save(reference, file, ResourceSaver.FLAG_COMPRESS) == OK
	world.free()
	if not require(saved, "Cannot save the merged reference view"): return false
	if not add_file(BASE + "reference.scn", file): return false
	for dependency: String in dependencies(file):
		if not add_resource(dependency): return false
	return true

func make_static(node: Node, scene_root: Node, embedded: Dictionary) -> void:
	if node is Timer: node.stop()
	for signal_info: Dictionary in node.get_signal_list():
		for connection: Dictionary in node.get_signal_connection_list(signal_info.name):
			node.disconnect(signal_info.name, connection.callable)
	for key: StringName in node.get_meta_list():
		if node.get_meta(key) is Object: node.remove_meta(key)
	node.set_script(null)
	node.scene_file_path = ""
	if str(node.name).begins_with("@"): node.name = "CapturedNode_%d" % node.get_index()
	if node != scene_root: node.owner = scene_root
	for child: Node in node.get_children():
		make_static(child, scene_root, embedded)
	embed_resources(node, embedded)

func embed_resources(object: Object, embedded: Dictionary) -> void:
	for property: Dictionary in object.get_property_list():
		if property.usage & PROPERTY_USAGE_STORAGE and property.name != "resource_path":
			embed_value(object.get(property.name), embedded)

func embed_value(value: Variant, embedded: Dictionary) -> void:
	if value is Resource and not (value is Texture or value is Shader or value is Script):
		var identity: int = value.get_instance_id()
		if embedded.has(identity): return
		embedded[identity] = true
		value.resource_path = ""
		embed_resources(value, embedded)
	elif value is Dictionary or value is Array:
		var items: Array = value.values() if value is Dictionary else value
		for item: Variant in items:
			embed_value(item, embedded)

func run() -> void:
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(INDEX))
	var entries: Dictionary = index.fileGraph.entries
	var previews: Dictionary = index.previews
	if not require(DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT)) == OK, "Cannot create review build directory"): return
	var pack_path := OUTPUT + "nest-assets.pck"
	if not require(pack.pck_start(pack_path) == OK, "Cannot start formal asset pack"): return
	for id: String in entries:
		var entry: Dictionary = entries[id]
		var path := NEST + str(entry.file)
		if entry.kind != "source" and not verify_scene_links(path, entry, entries): return
		if not add_resource(path): return
		previews[id].merge({"path": path, "source": entry.kind == "source", "focus": entry.get("focus", [])}, true)
	previews["reassembled"] = {"path": previews["view:estate-layout"].path, "base": "reassembled"}
	if not pack_reference(): return
	if not (add_generated("res://project.godot", SHELL)
		and add_generated("res://review.tscn", REVIEW_SCENE)
		and add_generated("res://.godot/global_script_class_cache.cfg", "list=[]\n")
		and add_file("res://.godot/uid_cache.bin", "res://.godot/uid_cache.bin")
		and add_generated(BASE + "menu.json", JSON.stringify(entries.keys()))
		and add_generated(BASE + "asset-previews.json", JSON.stringify(previews))
		and add_file("res://review.gd", CONTROLLER_PATH)
		and require(pack.flush() == OK, "Cannot finish formal asset pack")): return

	if not require(ProjectSettings.load_resource_pack(pack_path, false), "Cannot mount formal asset pack"): return
	var viewer: Node3D = CONTROLLER.new()
	root.add_child(viewer)
	var geometry := {}
	for id: String in entries:
		geometry[id] = viewer.show_scene(id, false, previews[id].focus, id == "view:estate-layout")
		if not require(geometry[id] > 0, "Empty formal asset preview: " + id): return
		var groups: Array = previews[id].get("groups", [])
		if not groups.is_empty():
			var expected := 0
			for group: Array in groups:
				expected += group.size()
			if not require(geometry[id] == expected, "Prototype preview count differs for " + id): return
	for id: String in ["reference", "reassembled"]:
		if not require(viewer.show_scene(id) > 0, "Empty estate comparison: " + id): return
	viewer.free()
	var report := {
		"assets": geometry,
		"index_sha256": FileAccess.get_sha256(INDEX),
		"controller_sha256": FileAccess.get_sha256(CONTROLLER_PATH),
		"pack_sha256": FileAccess.get_sha256(pack_path),
		"source_hashes": source_hashes,
	}
	if not write(OUTPUT + "report.json", JSON.stringify(report, "  ")): return
	print("NEST_ASSET_PACK_READY assets=", geometry.size(), " packed_files=", packed.size())
	quit(0)
