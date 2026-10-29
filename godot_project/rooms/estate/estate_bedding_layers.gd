extends RefCounted
## The original sewn hem and white throw ride on the same green cloth surface.
const CELL := 0.05
var cloth: MeshInstance3D
var rest: Mesh
var layers: Array[Dictionary] = []
var _points: PackedVector3Array
var _cells: Dictionary = {}
var _last: Mesh

static func attach(estate: Node) -> void:
	var beds: Dictionary = {}
	var meshes := estate.find_children("*", "MeshInstance3D", true, false)
	for mesh: MeshInstance3D in meshes:
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("piece") != "bed_cover": continue
		var key := str(e.get("module"))+":"+str(e.get("resident"))
		if not mesh.has_meta("estate_bedding_layers"):
			var binding: RefCounted = (load("res://rooms/estate/estate_bedding_layers.gd") as Script).new()
			binding._bind(mesh)
			mesh.set_meta("estate_bedding_layers", binding)
		beds[key] = mesh.get_meta("estate_bedding_layers")
	for mesh: MeshInstance3D in meshes:
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("piece") not in ["throw", "bed_cover_seam"]: continue
		var key := str(e.get("module"))+":"+str(e.get("resident"))
		if beds.has(key): beds[key]._add(mesh, e.get("piece") == "throw")
	for binding: RefCounted in beds.values(): binding.sample()

func _bind(value: MeshInstance3D) -> void:
	cloth = value
	rest = cloth.mesh
	_points = rest.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = rest.surface_get_arrays(0)[Mesh.ARRAY_INDEX]
	for i in range(0, indices.size(), 3):
		var ids := Vector3i(indices[i], indices[i+1], indices[i+2])
		var a := _points[ids.x]
		var b := _points[ids.y]
		var c := _points[ids.z]
		for x in range(floori(minf(a.x,minf(b.x,c.x))/CELL), floori(maxf(a.x,maxf(b.x,c.x))/CELL)+1):
			for z in range(floori(minf(a.z,minf(b.z,c.z))/CELL), floori(maxf(a.z,maxf(b.z,c.z))/CELL)+1):
				var key := Vector2i(x,z)
				if not _cells.has(key): _cells[key] = []
				_cells[key].append(ids)

func _support(point: Vector3) -> Dictionary:
	var key := Vector2i(floori(point.x/CELL), floori(point.z/CELL))
	var height := -INF
	var result: Dictionary = {}
	var nearest := INF
	var closest := 0
	for ids: Vector3i in _cells.get(key, []):
		var a := _points[ids.x]
		var ab := Vector2(_points[ids.y].x-a.x, _points[ids.y].z-a.z)
		var ac := Vector2(_points[ids.z].x-a.x, _points[ids.z].z-a.z)
		var ap := Vector2(point.x-a.x, point.z-a.z)
		var determinant := ab.cross(ac)
		if absf(determinant) < 0.00000001: continue
		var v := ap.cross(ac)/determinant
		var w := ab.cross(ap)/determinant
		var weights := Vector3(1.0-v-w, v, w)
		var y := a.y*weights.x+_points[ids.y].y*v+_points[ids.z].y*w
		if weights.x>=-0.0001 and v>=-0.0001 and w>=-0.0001 and y>height:
			height = y
			result = {"ids": ids, "weights": weights}
	if not result.is_empty(): return result
	# A few fringe tips overhang the cloth outline. Carry their original X/Z
	# offset from the nearest supported hem instead of pinning them in space.
	for i in range(_points.size()):
		var distance := Vector2(point.x-_points[i].x, point.z-_points[i].z).length_squared()
		if distance < nearest:
			nearest = distance
			closest = i
	return {"ids": Vector3i(closest,closest,closest), "weights": Vector3(1,0,0)}

func _add(mesh: MeshInstance3D, white: bool) -> void:
	if mesh.has_meta("estate_bedding_bound"): return
	mesh.set_meta("estate_bedding_bound", true)
	var frame := cloth.global_transform.affine_inverse()*mesh.global_transform
	var surfaces: Array[Dictionary] = []
	var source := mesh.mesh
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		var original: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var ids: Array[Vector3i] = []
		var weights := PackedVector3Array()
		var offsets := PackedVector3Array()
		for local: Vector3 in original:
			var point := frame*local
			var support := _support(point)
			var corners: Vector3i = support["ids"]
			var blend: Vector3 = support["weights"]
			var base := _points[corners.x]*blend.x+_points[corners.y]*blend.y+_points[corners.z]*blend.z
			var small_fold := (local.y-source.get_aabb().position.y)*0.025 if white else 0.0
			point.y = base.y+(0.006+small_fold if white else 0.001)
			ids.append(corners)
			weights.append(blend)
			offsets.append(point-base)
		surfaces.append({"arrays": arrays, "ids": ids, "weights": weights, "offsets": offsets, "material": source.surface_get_material(surface)})
	layers.append({"mesh": mesh, "surfaces": surfaces, "inverse": frame.affine_inverse(), "rest": null, "dynamic": ArrayMesh.new()})

func sample() -> void:
	if cloth.mesh == rest and _last == rest: return
	var points: PackedVector3Array = cloth.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for layer: Dictionary in layers:
		var mesh: MeshInstance3D = layer["mesh"]
		if cloth.mesh == rest and layer["rest"] != null:
			mesh.mesh = layer["rest"]
			continue
		var result := ArrayMesh.new() if cloth.mesh == rest else layer["dynamic"] as ArrayMesh
		result.clear_surfaces()
		for surface: Dictionary in layer["surfaces"]:
			var arrays: Array = surface["arrays"].duplicate()
			var vertices := PackedVector3Array()
			var ids: Array = surface["ids"]
			var weights: PackedVector3Array = surface["weights"]
			var offsets: PackedVector3Array = surface["offsets"]
			for i in range(ids.size()):
				var corners: Vector3i = ids[i]
				var blend := weights[i]
				vertices.append(layer["inverse"]*(points[corners.x]*blend.x+points[corners.y]*blend.y+points[corners.z]*blend.z+offsets[i]))
			arrays[Mesh.ARRAY_VERTEX] = vertices
			arrays[Mesh.ARRAY_NORMAL] = _normals(vertices, arrays[Mesh.ARRAY_INDEX])
			arrays[Mesh.ARRAY_TANGENT] = null
			result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
			result.surface_set_material(result.get_surface_count()-1, surface["material"])
		mesh.mesh = result
		if cloth.mesh == rest: layer["rest"] = result
	_last = cloth.mesh

static func _normals(points: PackedVector3Array, indices: PackedInt32Array) -> PackedVector3Array:
	var normals := PackedVector3Array()
	normals.resize(points.size())
	for i in range(0, indices.size(), 3):
		var a := indices[i]
		var b := indices[i+1]
		var c := indices[i+2]
		var normal := (points[c]-points[a]).cross(points[b]-points[a])
		for corner: int in [a,b,c]: normals[corner] += normal
	for i in range(normals.size()): normals[i] = normals[i].normalized()
	return normals
