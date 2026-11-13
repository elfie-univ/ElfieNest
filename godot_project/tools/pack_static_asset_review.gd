extends "res://tools/reassemble_static_assets.gd"
## Relocate the verified split resources into a browser-local, non-authoritative pack.

const BASE := "res://v044-review/"
const STAGE := REVIEW + "/portable"

func add_file(pack: PCKPacker, to: String, from: String) -> bool:
	return check(pack.add_file(to, from) == OK, "Cannot pack " + from)

func run() -> void:
	var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(REVIEW.path_join("assembly-report.json")))
	if not check(report.passed and report.assembly_sha256 == FileAccess.get_sha256(REVIEW.path_join("reassembled.scn")), "Missing validated reassembly"): return
	var bindings: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(BINDINGS))
	var native: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(EXPORTED.path_join("export-report.json")))
	var models := {}
	var ids := []
	for item: Dictionary in bindings.items:
		ids.append(item.id)
		models["models/" + item.id + ".scn"] = load(EXPORTED.path_join("models/" + item.id + ".scn"))
	models["reference.scn"] = load(EXPORTED.path_join("v044-static-world.scn"))
	models["reassembled.scn"] = load(REVIEW.path_join("reassembled.scn"))
	var resources := {}
	for name: String in DirAccess.get_files_at(ProjectSettings.globalize_path(EXPORTED.path_join("resources"))):
		if not name.ends_with(".res"): continue
		var path := "resources/" + name
		var resource := load(EXPORTED.path_join(path))
		if not check(resource != null, "Cannot load native resource " + path): return
		resources[path] = resource
	if not check(resources.size() == native.resources_saved, "Native resource pool incomplete: " + str(resources.size())): return
	for path: String in resources:
		(resources[path] as Resource).take_over_path(BASE + path)
	for folder: String in ["models", "resources"]:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(STAGE.path_join(folder)))
	var pack_path := REVIEW.path_join("v044-assets.pck")
	var pack := PCKPacker.new()
	if not check(pack.pck_start(pack_path) == OK, "Cannot start pack"): return
	for files: Dictionary in [resources, models]:
		for path: String in files:
			var output := STAGE.path_join(path)
			if not check(ResourceSaver.save(files[path], output, ResourceSaver.FLAG_COMPRESS) == OK, "Cannot relocate " + path): return
			if not add_file(pack, BASE + path, output): return
	for path: String in native.dependencies:
		if not check(FileAccess.get_sha256(path) == native.dependencies[path], "Shader changed " + path): return
		if not add_file(pack, path, path): return
	var verification: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(EXPORTED.path_join("verification-report.json")))
	for path: String in verification.shader_dependencies:
		if native.dependencies.has(path): continue
		if not check(FileAccess.get_sha256(path) == verification.shader_dependencies[path], "Shader include changed " + path): return
		if not add_file(pack, path, path): return
	store_json(STAGE.path_join("menu.json"), ids)
	var files := {
		"res://project.godot": STAGE.path_join("project.godot"),
		"res://review.tscn": STAGE.path_join("review.tscn"),
		"res://.godot/global_script_class_cache.cfg": STAGE.path_join("empty-class-cache.cfg"),
		"res://v044-review/menu.json": STAGE.path_join("menu.json"),
		"res://review.gd": "res://tools/static_asset_review.gd",
	}
	for to: String in files:
		if not add_file(pack, to, files[to]): return
	if not check(pack.flush() == OK, "Cannot flush pack"): return
	if not check(ProjectSettings.load_resource_pack(pack_path, false), "Cannot mount generated review pack"): return
	var chair := ResourceLoader.load(BASE + "models/chair.scn", "PackedScene", ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
	if not check(chair != null, "Cannot reload portable chair"): return
	var sample := chair.instantiate()
	var count := 0
	for mesh: MeshInstance3D in sample.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh != null: count += 1
	sample.free()
	if not check(count > 0, "Portable chair geometry missing"): return
	print("V044_REVIEW_PACK_READY ", pack_path, " assets=", ids.size(), " resources=", resources.size())
	quit(0)
