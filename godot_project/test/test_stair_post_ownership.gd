extends SceneTree

const BUILDING := "res://nest/buildings/building-layout.scn"
const FOREST := "res://nest/courtyard/areas/forest/forest-layout.scn"
const LIBRARY := "res://nest/buildings/main/central-building.glb"
const BINDING := preload("res://nest/assembly/glb_placement.gd")

func _initialize() -> void:
	call_deferred("run")

static func validate_library(scene: Node3D) -> String:
	var prototype := scene.find_child("main_0426",true,false) as MeshInstance3D
	if prototype == null: return "The original rail-post prototype is missing"
	for name: String in ["main_0758", "main_0759"]:
		var post := scene.find_child(name,true,false) as MeshInstance3D
		if post == null or post.mesh != prototype.mesh:
			return "The landing post must share the original building post mesh: " + name
		var box := post.transform * post.get_aabb()
		if absf(box.position.y - 4.299) > 0.0001 or box.end.y < 5.1 or box.end.y > 5.18:
			return "The landing post lost its floor/handrail contact: " + name
	return ""

static func validate_assembly(scene: Node3D) -> String:
	var seen := {}
	for node: MeshInstance3D in scene.find_children("*","MeshInstance3D",true,false):
		var path := str(node.get_meta("v044_path",""))
		if not path.get_file().begins_with("LandingTerminalPost"): continue
		var binding := node.get_parent()
		if binding.get_script() != BINDING or binding.library.resource_path != LIBRARY:
			return "A landing post is outside the main building source"
		seen[path] = true
	return "" if seen.size() == 2 else "The building must contain both landing posts"

func run() -> void:
	var library := (load(LIBRARY) as PackedScene).instantiate() as Node3D
	var error := validate_library(library)
	library.free()
	if not error.is_empty():
		push_error(error)
		quit(1)
		return
	var building := (load(BUILDING) as PackedScene).instantiate() as Node3D
	error = validate_assembly(building)
	building.free()
	if not error.is_empty():
		push_error(error)
		quit(1)
		return
	print("STAIR_POST_SOURCE_AND_OWNERSHIP_OK")
	quit(0)
