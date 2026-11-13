extends RefCounted
## Conservative compound desktop silhouette, including its raised rounded joint.
## Project actual triangles; do not bridge the seat recess with a single hull.

static func bake(mesh: MeshInstance3D) -> ConcavePolygonShape3D:
	# Authoring only. Runtime loads the shared BVH from estate_spatial.res.
	var started := Time.get_ticks_msec()
	var faces := preload("res://nest/spatial/estate_physics.gd").collision_faces(mesh.mesh)
	var bounds := mesh.get_aabb()
	var expanded: Array[PackedVector2Array] = []
	var covered := {}
	for index in range(0,faces.size(),3):
		var polygon := PackedVector2Array()
		for offset in range(3): polygon.append(Vector2(faces[index+offset].x,faces[index+offset].z))
		var area := absf((polygon[1]-polygon[0]).cross(polygon[2]-polygon[0]))
		if area < 0.000000001: continue
		if Geometry2D.is_polygon_clockwise(polygon): polygon.reverse()
		# A union of closed triangular prisms has the same projected volume.
		# Keep it in one shared static BVH; no pairwise polygon union and no
		# thousands of separate convex bodies are needed, even during authoring.
		var outlines := Geometry2D.offset_polygon(polygon,0.001)
		# Almost edge-on triangles can collapse at the polygon library's precision.
		# Their vertices are checked against the remaining prisms below.
		if outlines.size() != 1: continue
		for point: Vector2 in polygon:
			if Geometry2D.is_point_in_polygon(point,outlines[0]): covered[point] = true
		expanded.append(outlines[0])
	if expanded.is_empty(): return null
	for point: Vector3 in faces:
		if not covered.has(Vector2(point.x,point.z)):
			var projection := Vector2(point.x,point.z)
			var contained := false
			for outline: PackedVector2Array in expanded:
				if Geometry2D.is_point_in_polygon(projection,outline):
					contained = true
					break
			if not contained:
				push_error("Desktop silhouette misses original vertex: " + str(point))
				return null
			covered[projection] = true
	var surface := PackedVector3Array()
	for outline: PackedVector2Array in expanded:
		var indices := Geometry2D.triangulate_polygon(outline)
		for index in range(0, indices.size(), 3):
			for height: float in [bounds.position.y, bounds.end.y]:
				for offset in range(3):
					var point := outline[indices[index+offset]]
					surface.append(Vector3(point.x,height,point.y))
		for index in range(outline.size()):
			var a := outline[index]
			var b := outline[(index+1)%outline.size()]
			var low_a := Vector3(a.x,bounds.position.y,a.y)
			var low_b := Vector3(b.x,bounds.position.y,b.y)
			var high_a := Vector3(a.x,bounds.end.y,a.y)
			var high_b := Vector3(b.x,bounds.end.y,b.y)
			surface.append_array(PackedVector3Array([low_a,low_b,high_a,low_b,high_b,high_a]))
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(surface)
	shape.backface_collision = true
	shape.set_meta("desktop_silhouette", true)
	shape.set_meta("original_vertex_containment", true)
	print("CHAIR_DESKTOP_BAKED original_triangles=",faces.size()/3," surface_triangles=",surface.size()/3," elapsed_ms=",Time.get_ticks_msec()-started)
	return shape
