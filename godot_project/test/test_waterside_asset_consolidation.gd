extends SceneTree

const BINDING := preload("res://nest/assembly/glb_placement.gd")
const FOUNTAIN := "res://nest/courtyard/parts/waterside/fountain.glb"
const LAKE := "res://nest/courtyard/parts/waterside/lake.glb"
const SCENES := ["res://nest/courtyard/areas/waterside/waterside-layout.scn", "res://nest/courtyard/overview/courtyard-all/courtyard-layout.scn"]

func _initialize() -> void:
	call_deferred("run")

static func validate(scene: Node3D) -> String:
	var waterfall := false
	for child: Node in scene.find_children("*","Node",true,false):
		if child.scene_file_path.ends_with("/fountain.scn"): return "A separate fountain scene wrapper remains"
	for binding: Node in scene.find_children("*", "Node3D", true, false):
		if binding.get_script() != BINDING: continue
		if binding.library == null: return "Missing water source library"
		if binding.library.resource_path.get_file() in ["waterfall.glb", "water-lilies.glb"]: return "A scene still uses a separate water component"
		if binding.source_nodes.size() != binding.get_child_count(): return "Water component binding count changed"
		for slot: int in binding.source_nodes.size():
			var node := binding.get_child(slot)
			if node is MeshInstance3D and node.mesh == null: return "Unbound water mesh"
			if node is MultiMeshInstance3D and (node.multimesh == null or node.multimesh.mesh == null): return "Unbound water batch"
			var path := str(node.get_meta("v044_path", ""))
			if path.ends_with("Continuous shallow waterfall from solid spillway crest"):
				if binding.library.resource_path != FOUNTAIN: return "Waterfall is outside the fountain file"
				if not node.get_active_material(0) is ShaderMaterial: return "Waterfall lost its animated shader"
				waterfall = true
			if "__ELFIE_INST_GROUP_016" in path or "__ELFIE_INST_GROUP_017" in path:
				if binding.library.resource_path != LAKE: return "Water lilies are outside the lake file"
	return "" if waterfall else "The combined fountain lost its waterfall"

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
	print("WATERSIDE_COMBINED_SOURCES_AND_ANIMATED_MATERIALS_OK")
	quit(0)
