extends SceneTree
## Snapshot current authored split fixtures; never regenerate a second lighting source.
func _initialize() -> void: call_deferred("run")

func run() -> void:
	var source := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(source)
	var fixtures := Node3D.new()
	fixtures.name = "CourtyardLighting"
	root.add_child(fixtures)
	for node: Node in source.find_children("*", "", true, false):
		if not (node is MeshInstance3D or node is Light3D): continue
		var extras: Dictionary = node.get_meta("extras", {})
		if not extras.has("outdoor_fixture_id"): continue
		var copy := node.duplicate(0) as Node3D
		fixtures.add_child(copy)
		copy.global_transform = node.global_transform
		copy.owner = fixtures
	var packed := PackedScene.new()
	assert(fixtures.get_child_count() > 0 and packed.pack(fixtures) == OK)
	var directory := ProjectSettings.globalize_path("res://../build/courtyard-lighting")
	DirAccess.make_dir_recursive_absolute(directory)
	assert(ResourceSaver.save(packed, directory.path_join("courtyard-lighting.scn"), ResourceSaver.FLAG_COMPRESS) == OK)
	print("SPLIT_LIGHTING_SNAPSHOT fixtures=", fixtures.get_child_count())
	source.free(); fixtures.free(); quit()
