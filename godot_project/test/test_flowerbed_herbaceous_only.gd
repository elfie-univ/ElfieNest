extends SceneTree
## Flowerbeds use herbaceous plants, never tree or woody-shrub prototypes.

const BINDING := preload("res://nest/assembly/glb_placement.gd")
const PLANTS := "res://nest/courtyard/parts/shared/plant-library.glb"
const AREAS := ["meadow", "waterside"]

func _initialize() -> void:
	call_deferred("run")

static func verify(scene: Node3D) -> String:
	var replacements := 0
	for binding: Node in scene.find_children("*", "Node3D", true, false):
		if binding.get_script() != BINDING: continue
		var path: String = binding.library.resource_path
		if path.get_file() in ["forest-wood.glb", "forest-foliage.glb", "forest-twigs.glb", "broadleaf-tree.glb", "pine-tree.glb", "tree-one.glb"]:
			return "Flowerbeds still contain tree or shrub resources: " + path
		if path == PLANTS and "part_00003" in binding.source_nodes:
			return "Flowerbeds still contain the mixed woody shrub"
		for child: Node in binding.get_children():
			if child.get_meta("herbaceous_replacement", false):
				if path != PLANTS: return "Replacement plants lost their shared herbaceous source"
				var source: String = binding.source_nodes[child.get_index()]
				if source not in ["part_00004", "part_00005", "part_00006", "part_00007", "part_00008", "part_00009", "part_00010", "part_00011", "part_00012", "part_00013", "part_00014", "part_00015", "part_00016"]:
					return "Unexpected replacement plant prototype"
				replacements += int(binding.instance_batches[child.get_index()].instance_count)
	return "" if replacements > 0 else "Removed shrubs were not replaced by flowers or grass"

const COVERAGE_POINTS := {
	"meadow": [Vector2(-17.5,47.7),Vector2(21.3,36.5),Vector2(1.7,51.1),Vector2(-0.1,50.5)],
	"waterside": [Vector2(22.5,-3.9),Vector2(40.3,3.7),Vector2(39.1,0.5)],
}
const POSES := preload("res://test/test_lotus_bay.gd")

static func covers(scene: Node3D, point: Vector2) -> bool:
	for binding: Node in scene.find_children("*","Node3D",true,false):
		if binding.get_script()!=BINDING or binding.library.resource_path!=PLANTS:continue
		for slot: int in binding.source_nodes.size():
			var child: Node3D=binding.get_child(slot)
			var mesh: Mesh=child.mesh if child is MeshInstance3D else child.multimesh.mesh
			if mesh==null:continue
			var base := POSES.pose_in(scene,child)
			var transforms: Array[Transform3D]=[]
			if binding.instance_batches.has(slot):
				var data: Dictionary=binding.instance_batches[slot]
				var stride := 12+(4 if data.use_colors else 0)+(4 if data.use_custom_data else 0)
				for instance: int in data.instance_count:
					var buffer: PackedFloat32Array=data.buffer
					var at := instance*stride
					transforms.append(base*Transform3D(Basis(Vector3(buffer[at],buffer[at+4],buffer[at+8]),Vector3(buffer[at+1],buffer[at+5],buffer[at+9]),Vector3(buffer[at+2],buffer[at+6],buffer[at+10])),Vector3(buffer[at+3],buffer[at+7],buffer[at+11])))
			else:transforms.append(base)
			for transform: Transform3D in transforms:
				var box: AABB=transform*mesh.get_aabb()
				if Rect2(Vector2(box.position.x,box.position.z),Vector2(box.size.x,box.size.z)).has_point(point):return true
	return false

func run() -> void:
	for area: String in AREAS:
		var scene := (load("res://nest/courtyard/areas/%s/%s-layout.scn" % [area, area]) as PackedScene).instantiate() as Node3D
		root.add_child(scene)
		var error := verify(scene)
		for point: Vector2 in COVERAGE_POINTS[area]:
			if not covers(scene,point):error="A former woody patch has no flower or grass coverage: "+str(point)
		scene.free()
		if not error.is_empty():
			push_error(error)
			quit(1)
			return
	print("HERBACEOUS_FLOWERBEDS_OK")
	quit(0)
