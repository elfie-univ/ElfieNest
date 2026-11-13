extends "res://tools/pack_static_asset_review.gd"
## Cold reload the exact browser pack before making it available to Nest Lab.

func run() -> void:
	var path := REVIEW.path_join("v044-assets.pck")
	if not check(ProjectSettings.load_resource_pack(path, false), "Cannot mount portable asset pack"): return
	var controller := load("res://review.gd") as Script
	if not check(controller != null and controller.can_instantiate(), "Portable review controller cannot compile"): return
	var ids: Array = JSON.parse_string(FileAccess.get_file_as_string(BASE + "menu.json"))
	var bindings: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(BINDINGS))
	var frozen: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OUT.path_join("after.json")))
	var reference := load(BASE + "reference.scn") as PackedScene
	var source_pool := load(EXPORTED.path_join("v044-static-world.scn")) as PackedScene
	if not check(reference != null and source_pool != null, "Cannot load review resource pools"): return
	var asset_count := 0
	for item: Dictionary in bindings.items:
		if not check(item.id in ids, "Pack menu is missing " + item.id): return
		var model := load(BASE + "models/" + item.id + ".scn") as PackedScene
		if not check(model != null, "Portable model failed " + item.id): return
		var instance := model.instantiate()
		var source := (load(EXPORTED.path_join("models/" + item.id + ".scn")) as PackedScene).instantiate()
		for selected: String in item.paths:
			var node := instance.get_node_or_null(NodePath(selected))
			if not check(node != null and signature(node) == signature(source.get_node(NodePath(selected))), "Portable asset changed: " + item.id + " " + selected): return
		instance.free()
		source.free()
		asset_count += 1
	var before := {}
	for version: String in ["reference", "reassembled"]:
		var instance := (load(BASE + version + ".scn") as PackedScene).instantiate()
		var after := inspect(instance)
		if not check(after.nodes == frozen.nodes and after.sharing == frozen.sharing, "Portable world differs from frozen V044: " + version): return
		for entry: Dictionary in JSON.parse_string(FileAccess.get_file_as_string(REVIEW.get_base_dir().path_join("full-inventory/static-nodes.json"))):
			var key: String = entry.path
			var node := instance.get_node(NodePath(key))
			if version == "reference": before[key] = signature(node)
			elif not check(before[key] == signature(node), "Portable world payload differs: " + key): return
		instance.free()
	if not check(asset_count == ids.size(), "Pack menu count mismatch"): return
	store_json(REVIEW.path_join("portable-report.json"), {"passed": true, "assets": asset_count, "nodes": before.size(), "frozen_sha256": bindings.snapshot_sha256, "pack_sha256": FileAccess.get_sha256(path)})
	print("V044_PORTABLE_PASS assets=", asset_count, " nodes=", before.size())
	quit(0)
