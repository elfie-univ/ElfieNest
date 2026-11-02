extends SceneTree
## Explicit offline authoring: publish the checked PackedScene from build/.
func _initialize() -> void: call_deferred("run")

func own(node: Node, owner_root: Node) -> void:
	for child: Node in node.get_children():
		child.owner = owner_root
		own(child,owner_root)

func run() -> void:
	var source := load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate() as Node3D
	root.add_child(source)
	var builder := preload("res://scripts/tools/outdoor_lighting_layout.gd").new()
	var layout := builder.build(source)
	if layout==null:
		quit(1)
		return
	own(layout,layout)
	print("V4_HIGH_POLES ",JSON.stringify(layout.get_meta("high_poles")))
	assert(layout.get_meta("fountain_rim").size() > 30, "Fountain contour missing")
	var packed := PackedScene.new()
	assert(packed.pack(layout) == OK)
	var directory := ProjectSettings.globalize_path("res://../build/estate-lighting-v4")
	DirAccess.make_dir_recursive_absolute(directory)
	assert(ResourceSaver.save(packed,directory.path_join("estate_outdoor_lighting.scn"),ResourceSaver.FLAG_COMPRESS) == OK)
	print("V5_LIGHTING_AUTHORED high=",layout.get_meta("high_poles").size()," forest=",layout.get_meta("forest_lamps").size()," edges=",layout.get_meta("road_edge_paths").size()," patterns=",layout.get_meta("plaza_pattern_paths").size()," patches=",layout.get_meta("ground_patches").size()," shoreline=",layout.get_meta("shoreline").size())
	quit(0)
