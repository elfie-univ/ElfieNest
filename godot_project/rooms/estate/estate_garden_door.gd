extends RefCounted
## Approved source-fit garden leaves shared by estate physics and visual review.
## No local clock, policy or Lab dependency; the existing door owner drives motion.

var opening_bounds := AABB()
var leaves: Array[Dictionary] = []
var _frame_vertices := PackedVector3Array()
var _root: Node3D


func build(parent: Node3D, source_frame: MeshInstance3D, front_glass: MeshInstance3D, collision_enabled: bool) -> Dictionary:
	_root = Node3D.new()
	_root.name = "GardenDoorLeaves"
	parent.add_child(_root)
	var bounds := source_frame.global_transform * source_frame.get_aabb()
	for surface in range(source_frame.mesh.get_surface_count()):
		var vertices: PackedVector3Array = source_frame.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
		for vertex: Vector3 in vertices:
			_frame_vertices.append(source_frame.global_transform * vertex)
	var center := bounds.get_center()
	var half_width := INF
	var top := INF
	for vertex: Vector3 in _frame_vertices:
		if vertex.y > bounds.position.y + 0.3 and vertex.y < center.y + 0.4:
			half_width = minf(half_width, absf(vertex.x - center.x))
		if absf(vertex.x - center.x) < bounds.size.x * 0.2 and vertex.y > center.y:
			top = minf(top, vertex.y)
	var bottom := bounds.position.y + 0.01
	half_width -= 0.01
	top -= 0.01
	opening_bounds = AABB(Vector3(center.x - half_width, bottom, center.z - 0.02), Vector3(half_width * 2.0, top - bottom, 0.04))
	var ivory := source_frame.get_active_material(0).duplicate() as Material
	var glazing := front_glass.get_active_material(0).duplicate() as Material
	for side in [-1, 1]:
		_add_leaf(side, glazing, ivory, source_frame.layers, collision_enabled)
	return {"root": _root, "opening_bounds": opening_bounds, "leaves": leaves}


func _add_leaf(side: int, glazing: Material, ivory: Material, layer_mask: int, collision_enabled: bool) -> void:
	var half_width := opening_bounds.size.x * 0.5
	var center := opening_bounds.get_center()
	var left := center.x - half_width if side < 0 else center.x + 0.002
	var right := center.x - 0.002 if side < 0 else center.x + half_width
	var leaf_center := Vector3((left + right) * 0.5, center.y, center.z)
	var leaf := Node3D.new()
	leaf.name = "GardenLeafLeft" if side < 0 else "GardenLeafRight"
	_root.add_child(leaf)
	leaf.set_meta("generated_garden_leaf", true)
	leaf.global_position = leaf_center
	var outline := PackedVector2Array([Vector2(left, opening_bounds.position.y), Vector2(right, opening_bounds.position.y)])
	for step in range(25):
		var x := lerpf(right, left, float(step) / 24.0)
		outline.append(Vector2(x, _profile_top(x)))
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	for point: Vector2 in outline:
		vertices.append(Vector3(point.x - leaf_center.x, point.y - leaf_center.y, 0.0))
		normals.append(Vector3.FORWARD)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = Geometry2D.triangulate_polygon(outline)
	var panel := ArrayMesh.new()
	panel.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var glass := MeshInstance3D.new()
	glass.name = "ExistingFacadeGlass"
	glass.mesh = panel
	glass.material_override = glazing
	glass.layers = layer_mask
	glass.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	leaf.add_child(glass)
	for index in range(outline.size()):
		var first := outline[index]
		var next := outline[(index + 1) % outline.size()]
		var delta := next - first
		var border := MeshInstance3D.new()
		var shape := BoxMesh.new()
		shape.size = Vector3(delta.length(), 0.025, 0.04)
		border.mesh = shape
		border.material_override = ivory
		border.layers = layer_mask
		leaf.add_child(border)
		var middle := (first + next) * 0.5
		border.position = Vector3(middle.x - leaf_center.x, middle.y - leaf_center.y, 0.0)
		border.rotation.z = atan2(delta.y, delta.x)
	var body := StaticBody3D.new()
	body.name = "GardenLeafCollision"
	# Production moves these bodies with the existing door controller. Review
	# uses the identical shape with collision disabled, outside authority maps.
	body.collision_layer = 1 if collision_enabled else 0
	body.collision_mask = 1 if collision_enabled else 0
	body.set_meta("source_node", "Central L1 rounded garden entrance")
	body.set_meta("estate_module", "central")
	body.set_meta("estate_floor", 1)
	_root.add_child(body)
	body.global_transform = leaf.global_transform
	var collision := CollisionShape3D.new()
	var shape := ConvexPolygonShape3D.new()
	var points := PackedVector3Array()
	for point: Vector2 in outline:
		for depth in [-0.02, 0.02]:
			points.append(Vector3(point.x - leaf_center.x, point.y - leaf_center.y, depth))
	# Include the exact border-box vertices, preserving the curved top instead
	# of placing the enclosing glass AABB across the portal's rounded corners.
	for border: MeshInstance3D in leaf.find_children("*", "MeshInstance3D", true, false):
		if border == glass:
			continue
		var local_frame := leaf.global_transform.affine_inverse() * border.global_transform
		for endpoint in range(8):
			points.append(local_frame * border.get_aabb().get_endpoint(endpoint))
	shape.points = points
	collision.shape = shape
	body.add_child(collision)
	var door := {"mesh": leaf, "body": body, "closed": leaf.global_transform, "offset": Vector3(float(side) * (right - left + 0.03), 0.0, 0.0), "center": leaf_center, "amount": 0.0}
	leaves.append(door)


func _profile_top(x: float) -> float:
	var height := opening_bounds.end.y
	for vertex: Vector3 in _frame_vertices:
		if absf(vertex.x - x) < 0.025 and vertex.y > opening_bounds.end.y - 0.4:
			height = minf(height, vertex.y - 0.01)
	return height
