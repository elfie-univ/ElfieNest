extends Node3D
## Whole authored planting surfaces, with internal triangulation walls removed.
const SOURCES := ["COMPLETE Scalloped front flower border", "CY R003 corrected CY R002 lakeside returned solid planting bank", "CY R003 corrected CY R002 lakeside gently sloping planted shore", "CY R003 corrected CY SHORE solid Continuous planted lake bank"]
var report: Dictionary = {}
var _coverage: Dictionary = {}
var _walkable: Array[PackedVector2Array] = []
var clip_holes := 0

func build(estate: Node3D, height_at: Callable, merge: Callable) -> void:
	for candidate: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var source := str((candidate.get_meta("extras",{}) as Dictionary).get("source_name",candidate.name))
		if source == "CY R003 circular waterfront platform closed foundation":
			_walkable.assign(merge.call(_top_faces(candidate)))
	var vertices := PackedVector3Array()
	var edges: Dictionary = {}
	var seen: Dictionary = {}
	var heights: Dictionary = {}
	var sources := PackedStringArray()
	var face_count := 0
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var source := str((mesh.get_meta("extras", {}) as Dictionary).get("source_name",mesh.name))
		if source not in SOURCES or mesh.mesh == null:
			continue
		sources.append(source)
		for triangle: PackedVector2Array in _top_faces(mesh):
			var keys: Array[String] = [_key(triangle[0]),_key(triangle[1]),_key(triangle[2])]
			keys.sort()
			var key: String = "|".join(keys)
			if seen.has(key):
				continue
			seen[key] = true
			for piece: PackedVector2Array in _clip_walkable(triangle):
				_index(piece)
				var bottom := PackedVector3Array()
				for point: Vector2 in piece:
					var point_key := _key(point)
					if not heights.has(point_key):
						heights[point_key] = float(height_at.call(point))+0.015
					bottom.append(Vector3(point.x,float(heights[point_key]),point.y))
				var cap := Geometry2D.triangulate_polygon(piece)
				face_count += cap.size()/3
				for index: int in cap:
					vertices.append(bottom[index]+Vector3.UP*2.0)
				for j in range(bottom.size()):
					var p: Vector3 = bottom[j]
					var q: Vector3 = bottom[(j+1)%bottom.size()]
					var edge_keys: Array[String] = [_key(Vector2(p.x,p.z)),_key(Vector2(q.x,q.z))]
					edge_keys.sort()
					var edge_key: String = "|".join(edge_keys)
					if edges.has(edge_key):
						edges[edge_key]["count"] += 1
					else:
						edges[edge_key] = {"count":1,"a":p,"b":q}
	var boundary_edges := 0
	for edge: Dictionary in edges.values():
		if int(edge["count"]) != 1:
			continue
		boundary_edges += 1
		var a: Vector3 = edge["a"]
		var b: Vector3 = edge["b"]
		vertices.append_array(PackedVector3Array([a,b,b+Vector3.UP*2.0,a,b+Vector3.UP*2.0,a+Vector3.UP*2.0]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var result := ArrayMesh.new()
	if not vertices.is_empty():
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color(0.88,0.14,0.19)
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var visual := MeshInstance3D.new()
	visual.name = "ContinuousAuthoredFlowerBeds"
	visual.mesh = result
	visual.material_override = material
	add_child(visual)
	report = {"source_surfaces":sources.size(),"sources":sources,"top_triangles":face_count,"boundary_edges":boundary_edges,"internal_edges_removed":edges.size()-boundary_edges,"walkable_masks":_walkable.size(),"unsupported_clip_holes":clip_holes}
	print("ESTATE_CONTINUOUS_BEDS "+JSON.stringify(report))

func _top_faces(mesh: MeshInstance3D) -> Array[PackedVector2Array]:
	var result: Array[PackedVector2Array] = []
	var frame: Transform3D = mesh.global_transform
	var normal_frame: Basis = frame.basis.inverse().transposed()
	for surface in range(mesh.mesh.get_surface_count()):
		var arrays: Array = mesh.mesh.surface_get_arrays(surface)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = PackedVector3Array() if arrays[Mesh.ARRAY_NORMAL] == null else arrays[Mesh.ARRAY_NORMAL]
		var indices: PackedInt32Array = PackedInt32Array() if arrays[Mesh.ARRAY_INDEX] == null else arrays[Mesh.ARRAY_INDEX]
		var size: int = points.size() if indices.is_empty() else indices.size()
		for offset in range(0,size,3):
			var ids := PackedInt32Array()
			for j in range(3):
				ids.append(offset+j if indices.is_empty() else indices[offset+j])
			var a: Vector3 = frame*points[ids[0]]
			var b: Vector3 = frame*points[ids[1]]
			var c: Vector3 = frame*points[ids[2]]
			var normal: Vector3 = -(b-a).cross(c-a).normalized()
			if not normals.is_empty():
				normal = normal_frame*(normals[ids[0]]+normals[ids[1]]+normals[ids[2]]).normalized()
			if normal.y <= 0.25:
				continue
			var triangle := PackedVector2Array([Vector2(a.x,a.z),Vector2(b.x,b.z),Vector2(c.x,c.z)])
			if absf((triangle[1]-triangle[0]).cross(triangle[2]-triangle[0])) > 0.000001:
				result.append(triangle)
	return result

func _clip_walkable(triangle: PackedVector2Array) -> Array[PackedVector2Array]:
	var pieces: Array[PackedVector2Array] = [triangle]
	for mask in _walkable:
		var next: Array[PackedVector2Array] = []
		for piece in pieces:
			var difference := Geometry2D.clip_polygons(piece,mask)
			var nested := false
			for i in range(difference.size()):
				for j in range(difference.size()):
					if i != j and Geometry2D.is_point_in_polygon(difference[j][0],difference[i]):
						nested = true
			if nested:
				clip_holes += 1
			else:
				next.append_array(difference)
		pieces = next
	return pieces

func walkable_contains(point: Vector2) -> bool:
	for mask in _walkable:
		if Geometry2D.is_point_in_polygon(point,mask):
			return true
	return false

func _key(point: Vector2) -> String:
	return str(Vector2i(roundi(point.x*1000),roundi(point.y*1000)))

func _index(triangle: PackedVector2Array) -> void:
	var bounds := Rect2(triangle[0],Vector2.ZERO)
	for point in triangle:
		bounds = bounds.expand(point)
	for x in range(floori(bounds.position.x/4),floori(bounds.end.x/4)+1):
		for y in range(floori(bounds.position.y/4),floori(bounds.end.y/4)+1):
			var cell := Vector2i(x,y)
			if not _coverage.has(cell):
				_coverage[cell] = []
			_coverage[cell].append(triangle)

func contains_point(point: Vector2) -> bool:
	var cell := Vector2i(floori(point.x/4),floori(point.y/4))
	for triangle: PackedVector2Array in _coverage.get(cell,[]):
		if Geometry2D.is_point_in_polygon(point,triangle):
			return true
	return false
