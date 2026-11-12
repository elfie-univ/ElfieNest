extends SceneTree
## Region ownership changes must preserve every tree placement and binding.

const BINDING := preload("res://nest/assembly/glb_placement.gd")
const BASE := "res://nest/courtyard/parts/forest/"
const LIBRARIES := [BASE+"tree-one.glb", BASE+"broadleaf-tree.glb", BASE+"pine-tree.glb", BASE+"forest-foliage.glb", BASE+"forest-twigs.glb"]
const SCENES := ["res://nest/courtyard/areas/forest/forest-layout/landmark-tree.scn", "res://nest/courtyard/areas/forest/forest-layout.scn", "res://nest/courtyard/areas/meadow/meadow-layout.scn", "res://nest/courtyard/areas/waterside/waterside-layout.scn", "res://nest/courtyard/areas/forest/forest-layout/branching-trees.scn", "res://nest/courtyard/areas/forest/forest-layout/broadleaf-trees.scn", "res://nest/courtyard/areas/forest/forest-layout/pine-trees.scn"]
const EXPECTED := {
 "forest-layout.scn":["tree-one.glb","broadleaf-tree.glb","pine-tree.glb","forest-foliage.glb","forest-twigs.glb"],
 "landmark-tree.scn":["tree-one.glb","forest-foliage.glb","forest-twigs.glb"],
 "branching-trees.scn":["tree-one.glb","forest-foliage.glb","forest-twigs.glb"],
 "broadleaf-trees.scn":["broadleaf-tree.glb","forest-foliage.glb","forest-twigs.glb"],
 "pine-trees.scn":["pine-tree.glb"],
 "meadow-layout.scn":[],"waterside-layout.scn":[],
}

func _initialize() -> void:
	call_deferred("run")

static func validate(scene: Node3D) -> String:
	var found := {}
	for node: Node in scene.find_children("*","Node3D",true,false):
		if node.get_script() != BINDING: continue
		if node.library == null: return "A scene lost its source library"
		var path: String = node.library.resource_path
		if path.get_file() not in ["tree-one.glb","broadleaf-tree.glb","pine-tree.glb","forest-foliage.glb","forest-twigs.glb","forest-wood.glb"]: continue
		if path not in LIBRARIES: return "A tree source is outside the forest category: " + path
		found[path] = true
		if node.source_nodes.size() != node.get_child_count(): return "A tree placement list is incomplete"
		for child: Node in node.get_children():
			if child is MeshInstance3D and child.mesh == null: return "An unbound tree mesh remains"
			if child is MultiMeshInstance3D and (child.multimesh == null or child.multimesh.mesh == null): return "An unbound tree instance batch remains"
	var actual := []
	for path: String in found:actual.append(path.get_file())
	actual.sort()
	var expected: Array=EXPECTED[scene.scene_file_path.get_file()].duplicate()
	expected.sort()
	return "" if actual==expected else "A tree class lost a source or a flowerbed references tree resources: "+scene.scene_file_path

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
	print("THREE_COMPLETE_TREE_CLASSES_AND_SOURCE_OWNERSHIP_OK")
	quit(0)
