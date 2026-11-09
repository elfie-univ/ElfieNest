extends SceneTree
## Region ownership changes must preserve every tree placement and binding.

const BINDING := preload("res://nest/assembly/glb_placement.gd")
const LIBRARIES := ["res://nest/courtyard/parts/forest/forest-wood.glb", "res://nest/courtyard/parts/forest/forest-foliage.glb"]
const SCENES := ["res://nest/courtyard/areas/forest/forest-layout/landmark-tree.scn", "res://nest/courtyard/areas/forest/forest-layout.scn", "res://nest/courtyard/areas/meadow/meadow-layout.scn", "res://nest/courtyard/areas/waterside/waterside-layout.scn"]

func _initialize() -> void:
	call_deferred("run")

static func validate(scene: Node3D) -> String:
	var found := {}
	for node: Node in scene.find_children("*","Node3D",true,false):
		if node.get_script() != BINDING: continue
		if node.library == null: return "A scene lost its source library"
		var path: String = node.library.resource_path
		if path.get_file() not in ["forest-wood.glb","forest-foliage.glb"]: continue
		if path not in LIBRARIES: return "A tree source is outside the forest category: " + path
		found[path] = true
		if node.source_nodes.size() != node.get_child_count(): return "A tree placement list is incomplete"
		for child: Node in node.get_children():
			if child is MeshInstance3D and child.mesh == null: return "An unbound tree mesh remains"
			if child is MultiMeshInstance3D and (child.multimesh == null or child.multimesh.mesh == null): return "An unbound tree instance batch remains"
	return "" if found.size() == 2 else "A scene lost its wood or foliage source"

func run() -> void:
	for path: String in SCENES:
		var scene := (load(path) as PackedScene).instantiate() as Node3D
		root.add_child(scene)
		var error := validate(scene)
		scene.free()
		if not error.is_empty():
			push_error(error)
			quit(1)
			return
	print("FOREST_TREE_OWNERSHIP_AND_ALL_FOUR_CONSUMERS_OK")
	quit(0)
