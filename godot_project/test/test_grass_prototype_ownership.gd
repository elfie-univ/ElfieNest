extends SceneTree

const BINDING := preload("res://nest/assembly/glb_placement.gd")
const PLANTS := "res://nest/courtyard/parts/shared/plant-library.glb"
const LEAVES := "res://nest/courtyard/parts/forest/forest-foliage.glb"
const SCENES := ["res://nest/courtyard/areas/forest/forest-layout.scn", "res://nest/courtyard/areas/waterside/waterside-layout.scn", "res://nest/courtyard/areas/meadow/meadow-layout.scn"]

func _initialize() -> void:
	call_deferred("run")

static func is_grass(path: String) -> bool:
	return "__ELFIE_INST_GROUP_030" in path

static func validate_sources() -> String:
	var plants := (load(PLANTS) as PackedScene).instantiate() as Node3D
	var leaves := (load(LEAVES) as PackedScene).instantiate() as Node3D
	var grass := plants.find_child("part_00016",true,false) as MeshInstance3D
	var error := ""
	if grass == null or grass.mesh == null or grass.mesh.get_faces().is_empty(): error = "The shared grass prototype is missing"
	for node: Node in leaves.find_children("*","MeshInstance3D",true,false):
		if str(node.get_meta("extras",{}).get("source_name","")) == "__ELFIE_INST_GROUP_030": error = "Grass is still stored with tree leaves"
	plants.free()
	leaves.free()
	return error

static func validate_scene(scene: Node3D) -> Dictionary:
	var count := 0
	for binding: Node in scene.find_children("*","Node3D",true,false):
		if binding.get_script() != BINDING: continue
		for slot: int in binding.source_nodes.size():
			var node := binding.get_child(slot)
			if not is_grass(str(node.get_meta("v044_path",""))): continue
			if binding.library.resource_path != PLANTS or str(binding.source_nodes[slot]) != "part_00016":
				return {"error":"Wrong grass reference at %s: %s/%s" % [scene.get_path_to(node), binding.library.resource_path, binding.source_nodes[slot]]}
			if node is MeshInstance3D and node.mesh == null: return {"error":"Unbound grass mesh"}
			if node is MultiMeshInstance3D and (node.multimesh == null or node.multimesh.mesh == null): return {"error":"Unbound grass batch"}
			count += 1
	return {"error":"" if count > 0 else "A region lost its grass", "references":count}

func run() -> void:
	var error := validate_sources()
	if not error.is_empty():
		push_error(error)
		quit(1)
		return
	var count := 0
	for path: String in SCENES:
		var scene := (load(path) as PackedScene).instantiate() as Node3D
		root.add_child(scene)
		var result := validate_scene(scene)
		scene.free()
		if not str(result.error).is_empty():
			push_error(result.error)
			quit(1)
			return
		count += int(result.references)
	if count != 44:
		push_error("The regional grass reference count changed")
		quit(1)
		return
	print("SHARED_GRASS_PROTOTYPE_AND_44_REGIONAL_REFERENCES_OK")
	quit(0)
