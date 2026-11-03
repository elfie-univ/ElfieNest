extends RefCounted
## Conservative compound slab for the stationary sample desktop only.
## Retains the original concave outline; never uses one hull across its recess.


static func create(mesh: MeshInstance3D) -> StaticBody3D:
	var faces := preload("res://rooms/estate/estate_physics.gd").collision_faces(mesh.mesh)
	var bounds := mesh.get_aabb()
	var outline := _top_outline(faces, bounds.end.y)
	if outline.is_empty(): return null
	outline = _remove_redundant_points(outline)
	var expanded := Geometry2D.offset_polygon(outline, 0.001)
	if expanded.size() != 1: return null
	outline = expanded[0]
	# Prove this proxy never shrinks away any original desktop vertex.
	for point: Vector3 in faces:
		if not Geometry2D.is_point_in_polygon(Vector2(point.x, point.z), outline):
			push_error("Desktop silhouette envelope does not contain the original mesh")
			return null
	var pieces := Geometry2D.decompose_polygon_in_convex(outline)
	if pieces.is_empty(): return null
	var body := StaticBody3D.new()
	body.set_meta("source_node", String(mesh.name))
	body.set_meta("original_vertex_containment", true)
	for polygon: PackedVector2Array in pieces:
		var points := PackedVector3Array()
		for point: Vector2 in polygon:
			points.append(Vector3(point.x, bounds.position.y, point.y))
			points.append(Vector3(point.x, bounds.end.y, point.y))
		var hull := ConvexPolygonShape3D.new()
		hull.points = points
		var collision := CollisionShape3D.new()
		collision.shape = hull
		body.add_child(collision)
	print("CHAIR_DESKTOP_PROXY original_triangles=", faces.size() / 3, " convex_slabs=", pieces.size(), " envelope_mm=1 all_vertices_contained=true")
	return body


static func _remove_redundant_points(outline: PackedVector2Array) -> PackedVector2Array:
	var changed := true
	while changed and outline.size() > 3:
		changed = false
		for index in range(outline.size() - 1, -1, -1):
			var previous := outline[(index - 1 + outline.size()) % outline.size()]
			var next := outline[(index + 1) % outline.size()]
			var closest := Geometry2D.get_closest_point_to_segment(outline[index], previous, next)
			if outline[index].distance_to(closest) < 0.0002:
				outline.remove_at(index)
				changed = true
	return outline


static func _top_outline(faces: PackedVector3Array, top: float) -> PackedVector2Array:
	var ids: Dictionary = {}
	var points: Array[Vector2] = []
	var edges: Dictionary = {}
	for index in range(0, faces.size(), 3):
		if minf(faces[index].y, minf(faces[index + 1].y, faces[index + 2].y)) < top - 0.000002: continue
		var triangle: Array[int] = []
		for offset in range(3):
			var point := Vector2(faces[index + offset].x, faces[index + offset].z)
			if not ids.has(point):
				ids[point] = points.size()
				points.append(point)
			triangle.append(int(ids[point]))
		for edge in range(3):
			var a := triangle[edge]
			var b := triangle[(edge + 1) % 3]
			if a == b: continue
			var key := Vector2i(mini(a, b), maxi(a, b))
			edges[key] = int(edges.get(key, 0)) + 1
	var neighbors: Dictionary = {}
	for edge: Vector2i in edges:
		if int(edges[edge]) != 1: continue
		if not neighbors.has(edge.x): neighbors[edge.x] = []
		if not neighbors.has(edge.y): neighbors[edge.y] = []
		(neighbors[edge.x] as Array).append(edge.y)
		(neighbors[edge.y] as Array).append(edge.x)
	if neighbors.is_empty(): return PackedVector2Array()
	for adjacent: Array in neighbors.values():
		if adjacent.size() != 2: return PackedVector2Array()
	var first := int(neighbors.keys()[0])
	var current := first
	var previous := -1
	var result := PackedVector2Array()
	while result.size() <= neighbors.size():
		result.append(points[current])
		var adjacent: Array = neighbors[current]
		var next := int(adjacent[0]) if int(adjacent[0]) != previous else int(adjacent[1])
		previous = current
		current = next
		if current == first: break
	if result.size() != neighbors.size(): return PackedVector2Array()
	if Geometry2D.is_polygon_clockwise(result): result.reverse()
	return result
