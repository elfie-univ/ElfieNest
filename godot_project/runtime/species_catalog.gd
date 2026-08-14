class_name SpeciesCatalog
extends RefCounted


static func discover_actor_scenes() -> Dictionary:
	"""Discover one actor scene per character directory without a code allowlist."""
	var catalog := {}
	var directory := DirAccess.open("res://characters")
	if directory == null:
		return catalog
	directory.list_dir_begin()
	while true:
		var entry := directory.get_next()
		if entry.is_empty():
			break
		if not directory.current_is_dir() or entry in ["shared", "animation", "tools"]:
			continue
		var scene_path := "res://characters/%s/%s.tscn" % [entry, entry]
		if ResourceLoader.exists(scene_path):
			var scene := load(scene_path) as PackedScene
			if scene != null:
				catalog[entry] = scene
	directory.list_dir_end()
	return catalog
