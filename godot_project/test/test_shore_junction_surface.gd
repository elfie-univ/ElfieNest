extends SceneTree
## Check the imported geometry at both lake-to-spillway shoulders.

const GROUND := "res://nest/courtyard/parts/ground/shared-ground.glb"

func _initialize() -> void:
	call_deferred("run")

static func validate_library(scene: Node3D) -> String:
	var body := scene.find_child("part_00000", true, false) as MeshInstance3D
	if body == null or body.mesh == null:
		return "The imported terrain mesh is missing"
	var arrays := body.mesh.surface_get_arrays(0)
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	for point: Vector3 in points:
		if point.x <= 24.2 or point.x >= 24.64 or point.y < -0.2: continue
		if absf(point.z - 27.59356) < 0.00001 or absf(point.z - 30.15356) < 0.00001:
			if absf(point.y + 0.051) > 0.00001:
				return "A raised end cap remains at %s" % point
	var winding := 0.0
	for at: int in range(0, indices.size(), 3):
		var a := points[indices[at]]
		var b := points[indices[at + 1]]
		var c := points[indices[at + 2]]
		var cross_y := (b - a).cross(c - a).y
		if absf(a.y - b.y) + absf(a.y - c.y) < 0.00001 and absf(cross_y) > 0.01 and normals[indices[at]].y > 0.99:
			winding = signf(cross_y)
			break
	if winding == 0.0:
		return "Cannot establish the imported land winding"
	var seen := [0, 0]
	for at: int in range(0, indices.size(), 3):
		var a := points[indices[at]]
		var b := points[indices[at + 1]]
		var c := points[indices[at + 2]]
		var center := (a + b + c) / 3.0
		if center.x <= 23.95 or center.x >= 25.15 or minf(a.y, minf(b.y, c.y)) < -0.2: continue
		var side := -1
		if center.z > 27.1 and center.z < 27.75: side = 0
		if center.z > 30.0 and center.z < 30.7: side = 1
		if side < 0: continue
		seen[side] += 1
		# Import compression can move coincident XZ coordinates by micrometres.
		if (b - a).cross(c - a).y * winding < -0.0000001:
			return "The imported shore folds beneath the land at %s" % center
	if seen[0] == 0 or seen[1] == 0:
		return "A spillway shoulder is missing"
	return ""

func run() -> void:
	var scene := (load(GROUND) as PackedScene).instantiate() as Node3D
	var error := validate_library(scene)
	scene.free()
	if not error.is_empty():
		push_error(error)
		quit(1)
		return
	print("SHORE_JUNCTION_SURFACE_OK")
	quit(0)
