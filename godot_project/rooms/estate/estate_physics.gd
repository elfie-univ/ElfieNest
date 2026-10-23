extends Node3D

## Physical proxies follow the approved geometry, never the retired layout.
const SOURCE_GROUP := &"complete_estate_navigation_source"
var collider_count := 0
var _static: Node3D
var _shapes: Dictionary = {}
var _geometry_signatures: Dictionary = {}
var _doors: Array[Dictionary] = []
var _stair_landings: Dictionary = {}
var _stair_upper_flights: Dictionary = {}
var _stair_lower_flights: Dictionary = {}


func build(estate: Node3D) -> void:
	_static = Node3D.new()
	_static.name = "StaticGeometry"
	add_child(_static)
	_static.add_to_group(SOURCE_GROUP)
	for body: StaticBody3D in estate.find_children("*", "StaticBody3D", true, false):
		body.add_to_group(SOURCE_GROUP)
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or is_instancing_template(mesh):
			continue
		var e := mesh.get_meta("extras", {}) as Dictionary
		var module := str(e.get("module", ""))
		var source := str(e.get("source_name", mesh.name))
		if source == "STAIR • half landing": _stair_landings[module] = mesh
		if source == "STAIR • solid flight 1": _stair_upper_flights[module] = mesh
		if source == "STAIR • solid flight 0": _stair_lower_flights[module] = mesh
		if bool(e.get("door_leaf", false)):
			_add_door(mesh, e)
			continue
		if module.is_empty():
			if "Inset natural lake" in source or source == "Reference fountain water":
				_add_water_exclusion(mesh)
			continue
		if bool(e.get("furniture", false)):
			var piece := str(e.get("piece", ""))
			var kind := str(e.get("kind", ""))
			if piece in ["shell", "cabinet", "worktop", "chair_seat"] or kind in ["chair", "sofa", "table", "desk", "bookcase", "built_in_cabinet", "fixed_furniture", "daybed"]:
				_add_mesh(mesh, false)
			continue
		if uses_concave_collision(mesh):
			_add_mesh(mesh, true)
	print("ESTATE_PHYSICS colliders=%d sliding_doors=%d" % [collider_count, _doors.size()])


static func uses_concave_collision(mesh: MeshInstance3D) -> bool:
	var e := mesh.get_meta("extras", {}) as Dictionary
	var module := str(e.get("module", ""))
	if module.is_empty() or bool(e.get("furniture", false)) or bool(e.get("door_leaf", false)):
		return false
	var source := str(e.get("source_name", mesh.name))
	if " light" in source.to_lower() or " lamp" in source.to_lower() or "diffuse" in source.to_lower() or "concealed" in source.to_lower():
		return false
	if module == "central":
		return source.begins_with("Central") or source.begins_with("Public stair")
	return source.begins_with("ROOM •") or source.begins_with("STAIR •") or source.begins_with("CONNECTOR •") or source.begins_with("GUARD •")


static func is_instancing_template(mesh: Node) -> bool:
	# Presentation visibility (including headless authority) never disables
	# physical geometry. Only the explicit instancing source prototypes are skipped.
	var node := mesh
	while node != null:
		if str(node.name).begins_with("__ELFIE_INST_GROUP_"):
			return true
		node = node.get_parent()
	return false


func _add_mesh(mesh: MeshInstance3D, concave: bool, parent: Node3D = null) -> StaticBody3D:
	var mirrored := mesh.global_basis.determinant() < 0.0
	var resource_id := mesh.mesh.get_instance_id()
	var source_faces := PackedVector3Array()
	if not _geometry_signatures.has(resource_id):
		# Material variants can import as distinct ArrayMeshes with byte-identical
		# faces. Physics has no material/UV dependency: share the exact geometry,
		# retaining separate winding-corrected shapes for mirrored instances.
		var digest := HashingContext.new()
		digest.start(HashingContext.HASH_SHA256)
		source_faces = collision_faces(mesh.mesh)
		digest.update(source_faces.to_byte_array())
		_geometry_signatures[resource_id] = digest.finish().hex_encode()
	var key := "%s:%s:%s" % [_geometry_signatures[resource_id], str(concave), str(mirrored)]
	if not _shapes.has(key):
		var shape: Shape3D
		if concave:
			if source_faces.is_empty(): source_faces = collision_faces(mesh.mesh)
			var triangle_shape := ConcavePolygonShape3D.new()
			triangle_shape.set_faces(source_faces)
			shape = triangle_shape
		else:
			shape = mesh.mesh.create_convex_shape(true, false)
		if shape is ConcavePolygonShape3D:
			var triangle_shape := shape as ConcavePolygonShape3D
			if mirrored:
				var faces := triangle_shape.get_faces()
				for i in range(faces.size()):
					faces[i].x = -faces[i].x
				for i in range(0, faces.size(), 3):
					var temporary := faces[i + 1]
					faces[i + 1] = faces[i + 2]
					faces[i + 2] = temporary
				triangle_shape.set_faces(faces)
			triangle_shape.backface_collision = true
		elif mirrored and shape is ConvexPolygonShape3D:
			var hull := shape as ConvexPolygonShape3D
			var points := hull.points
			for i in range(points.size()):
				points[i].x = -points[i].x
			hull.points = points
		_shapes[key] = shape
	var body := StaticBody3D.new()
	body.name = "Collision_%d" % collider_count
	body.set_meta("source_node", str(mesh.name))
	var extras := mesh.get_meta("extras", {}) as Dictionary
	body.set_meta("estate_module", str(extras.get("module", "")))
	body.set_meta("estate_floor", int(extras.get("floor", 1)))
	(parent if parent != null else _static).add_child(body)
	body.global_transform = mesh.global_transform
	if mirrored:
		var positive_frame := body.global_transform
		positive_frame.basis.x = -positive_frame.basis.x
		body.global_transform = positive_frame
	var collision := CollisionShape3D.new()
	collision.shape = _shapes[key]
	body.add_child(collision)
	collider_count += 1
	return body


static func collision_faces(mesh: Mesh) -> PackedVector3Array:
	# Mesh.get_faces/create_trimesh_shape also create a cached picking BVH on
	# every render material variant. Read the same indexed triangles directly;
	# physics owns its own shared acceleration structure, not a second picking cache.
	var result := PackedVector3Array()
	for surface in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface)
		var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
		var indices := PackedInt32Array() if arrays[Mesh.ARRAY_INDEX] == null else arrays[Mesh.ARRAY_INDEX] as PackedInt32Array
		if indices.is_empty():
			result.append_array(vertices)
		else:
			var offset := result.size()
			result.resize(offset + indices.size())
			for i in range(indices.size()): result[offset + i] = vertices[indices[i]]
	return result


func _add_door(mesh: MeshInstance3D, e: Dictionary) -> void:
	var body := _add_mesh(mesh, false, self)
	var raw_axis: Array = e.get("slideAxis", [-1, 0, 0])
	var axis := Vector3(float(raw_axis[0]), float(raw_axis[1]), float(raw_axis[2]))
	var offset := mesh.global_basis * axis * float(e.get("slideTravelM", 1.5))
	_doors.append({"mesh": mesh, "body": body, "closed": mesh.global_transform, "offset": offset, "center": mesh.global_transform * mesh.get_aabb().get_center(), "amount": 0.0})


func _physics_process(delta: float) -> void:
	if _doors.is_empty(): return
	var actors := get_tree().get_nodes_in_group(&"runtime_elfie_actors")
	for door: Dictionary in _doors:
		var target := 0.0
		for actor: Node3D in actors:
			var center: Vector3 = door["center"]
			if Vector2(actor.global_position.x - center.x, actor.global_position.z - center.z).length() < 3.0 and absf(actor.global_position.y - (center.y - 1.2)) < 1.5:
				target = 1.0
				break
		door["amount"] = move_toward(float(door["amount"]), target, delta * 2.5)
		var frame: Transform3D = door["closed"]
		frame.origin += (door["offset"] as Vector3) * float(door["amount"])
		(door["mesh"] as Node3D).global_transform = frame
		if frame.basis.determinant() < 0.0:
			frame.basis.x = -frame.basis.x
		(door["body"] as Node3D).global_transform = frame


func _add_water_exclusion(mesh: MeshInstance3D) -> void:
	# A non-rendered exclusion volume prevents paths onto the submerged lake bed.
	# Its footprint is the actual water triangles, not a box over the shoreline.
	var source := mesh.mesh.get_faces()
	var faces := PackedVector3Array()
	for i in range(0, source.size(), 3):
		var a := mesh.global_transform * source[i]
		var b := mesh.global_transform * source[i + 1]
		var c := mesh.global_transform * source[i + 2]
		a.y = 2.4; b.y = 2.4; c.y = 2.4
		faces.append_array(PackedVector3Array([a, b, c]))
		for edge in [[a, b], [b, c], [c, a]]:
			var low_a: Vector3 = edge[0]; low_a.y = -2.0
			var low_b: Vector3 = edge[1]; low_b.y = -2.0
			faces.append_array(PackedVector3Array([edge[0], low_a, low_b, edge[0], low_b, edge[1]]))
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(faces)
	shape.backface_collision = true
	var body := StaticBody3D.new()
	body.name = "WaterExclusion_%d" % collider_count
	_static.add_child(body)
	body.global_transform = Transform3D.IDENTITY
	var collision := CollisionShape3D.new()
	collision.shape = shape
	body.add_child(collision)
	collider_count += 1


func bake(nest: Node3D) -> NavigationRegion3D:
	var region := NavigationRegion3D.new()
	region.name = "RuntimeNavigation"
	var nav := NavigationMesh.new()
	# Both species use a 1.72 x .34 capsule scaled by .7. Include appearance
	# limits (height 1.18, build 1.15) and recovery/grid clearance: maximum
	# physical height 1.421 m, radius .274 m, not the retired room agent.
	nav.agent_height = 1.45
	nav.agent_radius = 0.3
	nav.agent_max_climb = 0.2
	nav.agent_max_slope = 45.0
	nav.cell_size = 0.1
	nav.cell_height = 0.05
	nav.filter_baking_aabb = AABB(Vector3(-51, -0.12, -45), Vector3(102, 14, 102))
	nav.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	nav.geometry_source_geometry_mode = NavigationMesh.SOURCE_GEOMETRY_GROUPS_WITH_CHILDREN
	nav.geometry_source_group_name = SOURCE_GROUP
	var map := nest.get_world_3d().navigation_map
	NavigationServer3D.map_set_cell_size(map, nav.cell_size)
	NavigationServer3D.map_set_cell_height(map, nav.cell_height)
	region.navigation_mesh = nav
	nest.add_child(region)
	region.bake_navigation_mesh(false)
	_connect_stair_landings(region)
	print("ESTATE_NAVIGATION polygons=%d" % nav.get_polygon_count())
	return region


func _connect_stair_landings(region: Node3D) -> void:
	for module: String in _stair_landings:
		if not _stair_upper_flights.has(module) or not _stair_lower_flights.has(module): continue
		var landing := _stair_landings[module] as MeshInstance3D
		var flight := _stair_upper_flights[module] as MeshInstance3D
		var bounds := landing.global_transform * landing.get_aabb()
		var start := bounds.get_center()
		start.y = bounds.end.y + 0.02
		# Recast's voxel erosion can remove the narrow turning platform, or
		# attach its centre to the wrong flight depending on the pod's rotation.
		# Restore only the actual rectangular top, inset by the same body radius.
		var box := landing.get_aabb()
		var main_navigation := (region as NavigationRegion3D).navigation_mesh
		var radius := main_navigation.agent_radius
		var vertices := PackedVector3Array()
		for corner: Vector2 in [Vector2(box.position.x + radius, box.position.z + radius), Vector2(box.end.x - radius, box.position.z + radius), Vector2(box.end.x - radius, box.end.z - radius), Vector2(box.position.x + radius, box.end.z - radius)]:
			vertices.append(region.to_local(landing.global_transform * Vector3(corner.x, box.end.y + 0.02, corner.y)))
		var patch := NavigationRegion3D.new()
		patch.name = "StairTurningPlatform_" + module
		var navigation := NavigationMesh.new()
		navigation.cell_size = main_navigation.cell_size
		navigation.cell_height = main_navigation.cell_height
		navigation.set_vertices(vertices)
		var polygon := PackedInt32Array([0, 1, 2, 3])
		if landing.global_basis.determinant() < 0.0: polygon.reverse()
		navigation.add_polygon(polygon)
		patch.navigation_mesh = navigation
		region.add_child(patch)
		_add_stair_link(region, "StairLower_" + module, _tread_center(_stair_lower_flights[module], true), start)
		_add_stair_link(region, "StairUpper_" + module, start, _tread_center(flight, false))


func _tread_center(flight: MeshInstance3D, highest: bool) -> Vector3:
	var faces := collision_faces(flight.mesh)
	var first_height := -INF if highest else INF
	var total := Vector3.ZERO
	var total_area := 0.0
	for i in range(0, faces.size(), 3):
		var a := flight.global_transform * faces[i]
		var b := flight.global_transform * faces[i + 1]
		var c := flight.global_transform * faces[i + 2]
		var normal := (b - a).cross(c - a)
		if normal.length() < 0.00001 or absf(normal.normalized().y) < 0.99 or a.y < 0.5: continue
		if (highest and a.y > first_height + 0.001) or (not highest and a.y < first_height - 0.001):
			first_height = a.y
			total = Vector3.ZERO
			total_area = 0.0
		if absf(a.y - first_height) < 0.001:
			total += (a + b + c) / 3.0 * normal.length()
			total_area += normal.length()
	return total / total_area + Vector3.UP * 0.02 if total_area > 0.0 else Vector3.INF


func _add_stair_link(region: Node3D, label: String, start: Vector3, end: Vector3) -> void:
	if not start.is_finite() or not end.is_finite(): return
	var link := NavigationLink3D.new()
	link.name = label
	region.add_child(link)
	link.start_position = region.to_local(start)
	link.end_position = region.to_local(end)
	# Path seams on the solid turning platform: Actor movement never teleports.
