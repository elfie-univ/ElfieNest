extends Node3D

## Physical proxies follow the approved geometry, never the retired layout.
const DOOR := preload("res://rooms/estate/estate_door.gd")
const GARDEN_DOOR := preload("res://rooms/estate/estate_garden_door.gd")
const SOURCE_GROUP := &"complete_estate_navigation_source"
const OUTDOOR_ACCESS := preload("res://rooms/estate/estate_outdoor_access.gd")
const LAYERS := preload("res://runtime/world/collision_layers.gd")
const SPATIAL := preload("res://rooms/estate/estate_spatial_data.gd")
var outdoor_access: Node3D
var collider_count := 0
var _static: Node3D
var _shapes: Dictionary = {}
var _geometry_signatures: Dictionary = {}
var _doors: Array[Dictionary] = []
var _door_controls: Array[RefCounted] = []
var _doors_default_open := false
var _stair_landings: Dictionary = {}
var _stair_upper_flights: Dictionary = {}
var _stair_lower_flights: Dictionary = {}
var loaded_precompiled := false
var _spatial_data: Resource
var _source_estate: Node3D
var _captured_mesh_shapes: Dictionary = {}
var _authoring := false
var _complete_estate := false


func build(estate: Node3D, authoring: bool = false) -> void:
	_source_estate=estate
	_authoring=authoring
	_complete_estate=estate.find_child("COMPLETE Building garden island",true,false)!=null
	if not authoring and _complete_estate:
		if ResourceLoader.exists(SPATIAL.PATH):_spatial_data=load(SPATIAL.PATH)
		if _spatial_data==null or not _spatial_data.matches_inputs(SPATIAL.current_inputs()):
			push_error("Estate spatial resources are missing or stale. Run scripts/tools/bake_estate_spatial.gd before starting the world.")
			return
		loaded_precompiled=true
	_rebuild_garden_hardscape(estate)
	_static = Node3D.new()
	_static.name = "StaticGeometry"
	add_child(_static)
	_static.add_to_group(SOURCE_GROUP)
	if estate.find_child("COMPLETE Building garden island", true, false) != null:
		outdoor_access = OUTDOOR_ACCESS.new()
		outdoor_access.name = "OutdoorAccess"
		add_child(outdoor_access)
		if _spatial_data!=null:
			outdoor_access.load_precompiled(_spatial_data)
		elif not outdoor_access.build(estate):
			push_error("Complete estate outdoor access could not be built")
			return
		for boundary: StaticBody3D in outdoor_access.find_children("*", "StaticBody3D", true, false):
			boundary.add_to_group(SOURCE_GROUP)
		_restrict_background_obstacles(estate)
	for body: StaticBody3D in estate.find_children("*", "StaticBody3D", true, false):
		body.add_to_group(SOURCE_GROUP)
	var garden_frame: MeshInstance3D
	var garden_glass: MeshInstance3D
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or is_instancing_template(mesh):
			continue
		var e := mesh.get_meta("extras", {}) as Dictionary
		var module := str(e.get("module", ""))
		var source := str(e.get("source_name", mesh.name))
		if str(mesh.name) == "Central L1 rounded garden entrance": garden_frame = mesh
		if str(mesh.name) == "Central L1 curved front glass": garden_glass = mesh
		if source == "STAIR • half landing": _stair_landings[module] = mesh
		if source == "STAIR • solid flight 1": _stair_upper_flights[module] = mesh
		if source == "STAIR • solid flight 0": _stair_lower_flights[module] = mesh
		if bool(e.get("door_leaf", false)):
			_add_door(mesh, e)
			continue
		if e.has("outdoor_fixture_id"):
			if not bool(e.get("lighting_diffuser",false)) and not bool(e.get("lighting_flush",false)) and outdoor_access!=null:
				var point := (mesh.global_transform*mesh.get_aabb()).get_center()
				if outdoor_access.contains_outdoor_point(Vector2(point.x,point.z)):_add_mesh(mesh,false)
			continue
		if uses_furniture_collision(mesh):
			_add_mesh(mesh, false)
			continue
		if module.is_empty():
			if "Inset natural lake" in source or source == "Reference fountain water":
				_add_water_exclusion(mesh)
			continue
		if bool(e.get("furniture", false)):
			continue
		if uses_concave_collision(mesh):
			_add_mesh(mesh, true)
	if garden_frame != null and garden_glass != null:
		var generated: Dictionary = GARDEN_DOOR.new().build(self, garden_frame, garden_glass, true)
		for door: Dictionary in generated["leaves"]:
			_doors.append(door)
			_door_controls.append(DOOR.new(door))
			collider_count += 1
	print("ESTATE_PHYSICS colliders=%d sliding_doors=%d" % [collider_count, _doors.size()])


func _restrict_background_obstacles(estate: Node3D) -> void:
	for source: String in ["GardenCollision_TreeTrunks","GardenCollision_ShoreRocks","GardenCollision_Furniture"]:
		var body := estate.find_child(source,true,false) as StaticBody3D
		if body != null: _retain_accessible_obstacle(body)


func _retain_accessible_obstacle(source: StaticBody3D) -> void:
	# Keep occlusion separately. Closed planting/lake regions need no
	# individual movement bodies; real obstacles beside open ground still do.
	source.collision_layer = LAYERS.PERCEPTION_ONLY
	if _spatial_data!=null:
		var cached: Shape3D=_spatial_data.accessible_shapes.get(str(source.name))
		if cached!=null:
			var body := StaticBody3D.new()
			body.name="Accessible"+str(source.name).trim_prefix("GardenCollision_")
			_static.add_child(body);body.global_transform=Transform3D.IDENTITY
			var collision := CollisionShape3D.new();collision.shape=cached;body.add_child(collision)
		return
	var retained := PackedVector3Array()
	for collision: CollisionShape3D in source.find_children("*", "CollisionShape3D", true, false):
		var shape := collision.shape as ConcavePolygonShape3D
		if shape == null: continue
		var faces := shape.get_faces()
		for i in range(0,faces.size(),3):
			var triangle := PackedVector3Array()
			for j in range(3):
				var point := collision.global_transform*faces[i+j]
				triangle.append(point)
			# Keep the useful lower part of a tall proxy, without adding a
			# walkable cap. The original full proxy still provides occlusion.
			var clipped := PackedVector3Array()
			var previous := triangle[-1]
			for point: Vector3 in triangle:
				if (previous.y <= OUTDOOR_ACCESS.TOP) != (point.y <= OUTDOOR_ACCESS.TOP):
					clipped.append(previous.lerp(point,(OUTDOOR_ACCESS.TOP-previous.y)/(point.y-previous.y)))
				if point.y <= OUTDOOR_ACCESS.TOP: clipped.append(point)
				previous = point
			for j in range(1,clipped.size()-1):
				var middle := (clipped[0]+clipped[j]+clipped[j+1])/3.0
				if outdoor_access.contains_outdoor_point(Vector2(middle.x,middle.z)):
					retained.append_array(PackedVector3Array([clipped[0],clipped[j],clipped[j+1]]))
	if retained.is_empty(): return
	var body := StaticBody3D.new()
	body.name = "Accessible"+str(source.name).trim_prefix("GardenCollision_")
	body.set_meta("source_node",str(source.name))
	_static.add_child(body)
	body.global_transform = Transform3D.IDENTITY
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(retained);shape.backface_collision=true
	var collision := CollisionShape3D.new();collision.shape=shape;body.add_child(collision)
	print("OUTDOOR_OBSTACLE source=",source.name," movement_triangles=",retained.size()/3)


func _rebuild_garden_hardscape(estate: Node3D) -> void:
	# The merged authored proxy contains triangles spanning unrelated
	# paving and lake-bank pieces. Rebuild this one proxy from intact source meshes;
	# retain the real coping/rail geometry rather than treating it as walkable land.
	var body := estate.find_child("GardenCollision_Hardscape", true, false) as StaticBody3D
	if body == null:
		return
	if _spatial_data!=null:
		for shape: CollisionShape3D in body.find_children("*","CollisionShape3D",true,false):
			shape.transform=Transform3D.IDENTITY
			shape.shape=_spatial_data.hardscape_shape
		return
	var faces := PackedVector3Array()
	var sources := PackedStringArray()
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or is_instancing_template(mesh):
			continue
		var source := str((mesh.get_meta("extras", {}) as Dictionary).get("source_name", mesh.name))
		var forest_trail := bool((mesh.get_meta("extras", {}) as Dictionary).get("forestTrail", false))
		if not (forest_trail or source.begins_with("ROAD REF •") or source.begins_with("CY R001 ") or source.begins_with("CY R003 fountain connector ") or source.begins_with("Flower preview |") or source == "CY R003 circular waterfront platform closed foundation"):
			continue
		var frame := body.global_transform.affine_inverse() * mesh.global_transform
		for vertex: Vector3 in collision_faces(mesh.mesh):
			faces.append(frame * vertex)
		sources.append(source)
	if faces.is_empty():
		push_error("Cannot reconstruct authored garden hardscape surfaces")
		return
	var replacement := ConcavePolygonShape3D.new()
	replacement.set_faces(faces)
	replacement.backface_collision = true
	for shape: CollisionShape3D in body.find_children("*", "CollisionShape3D", true, false):
		shape.transform = Transform3D.IDENTITY
		shape.shape = replacement
		shape.set_meta("rebuilt_from_authored_surfaces", sources)
	print("ESTATE_HARDSCAPE_REBUILT source_meshes=%d triangles=%d" % [sources.size(), faces.size()/3])


static func uses_furniture_collision(mesh: MeshInstance3D) -> bool:
	var e := mesh.get_meta("extras", {}) as Dictionary
	var piece := str(e.get("piece", ""))
	var kind := str(e.get("kind", ""))
	if bool(e.get("furniture", false)) and (
		piece in ["shell", "cabinet", "worktop", "chair_seat", "chair_post", "chair_base", "chair_cushion", "drawer", "apron", "deck"]
		or kind in ["chair", "sofa", "table", "desk", "bookcase", "built_in_cabinet", "fixed_furniture", "daybed", "tv", "stool", "ottoman", "floor_cushion", "toy_box", "display_bank", "screen", "cabinet_doors", "cabinet_interior", "display"]
	):
		return true
	# The final asset also contains solid pieces with source names but no kind.
	# Collide with pots/supports, not every leaf, textile fringe or light diffuser.
	var source := str(e.get("source_name", mesh.name)).to_lower()
	return (
		"planter" in source or source.ends_with(" pot") or " bud vase" in source
		or source.begins_with("coffee table ") or source.begins_with("side table ")
		or (source.begins_with("upholstery ") and not " seam " in source)
		or source.begins_with("tv connected support ")
	)


static func uses_concave_collision(mesh: MeshInstance3D) -> bool:
	var e := mesh.get_meta("extras", {}) as Dictionary
	var module := str(e.get("module", ""))
	if module.is_empty() or bool(e.get("furniture", false)) or bool(e.get("door_leaf", false)):
		return false
	var source := str(e.get("source_name", mesh.name))
	# Final central assets use L1/Working/Roof01 names as well as Central/Public.
	# Roof petal shells contain light channels, but the shell itself is solid.
	if module == "central" and str(e.get("assembly", "")).begins_with("roof01_"):
		return true
	if " light" in source.to_lower() or " lamp" in source.to_lower() or "diffuse" in source.to_lower() or "concealed" in source.to_lower():
		return false
	if module == "central":
		if "luminous" in source.to_lower(): return false
		return (source.begins_with("Central") or source.begins_with("Public stair")
			or source.begins_with("L1 ") or source.begins_with("Rooftop stair ")
			or (source.begins_with("Working L") and "handrail shield" in source))
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
	var source_key := str(_source_estate.get_path_to(mesh))+":"+str(concave)+":"+str(mirrored)
	if _spatial_data!=null:
		assert(_spatial_data.mesh_shapes.has(source_key),"Compiled collider is missing: "+source_key)
		return _add_mesh_body(mesh,mirrored,_spatial_data.mesh_shapes[source_key],parent)
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
	_captured_mesh_shapes[source_key]=_shapes[key]
	return _add_mesh_body(mesh,mirrored,_shapes[key],parent)

func _add_mesh_body(mesh: MeshInstance3D,mirrored: bool,shape: Shape3D,parent: Node3D) -> StaticBody3D:
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
	collision.shape = shape
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
	var door := {"mesh": mesh, "body": body, "closed": mesh.global_transform, "offset": offset, "center": mesh.global_transform * mesh.get_aabb().get_center(), "amount": 0.0}
	_doors.append(door)
	_door_controls.append(DOOR.new(door))


func set_door_default_open(default_open: bool) -> void:
	# Supplied by the owning Nest environment projection, never inferred from
	# lamp visibility, quiet mode, the OS clock or an Observer's local time.
	_doors_default_open = default_open


func _physics_process(delta: float) -> void:
	if _door_controls.is_empty():
		return
	var actors: Array[Node3D] = []
	for node: Node in get_tree().get_nodes_in_group(&"runtime_elfie_actors"):
		if node is Node3D:
			actors.append(node)
	for control: RefCounted in _door_controls:
		control.advance(delta, _doors_default_open, actors)


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
	body.collision_layer = LAYERS.MOVEMENT_BOUNDARY
	_static.add_child(body)
	body.global_transform = Transform3D.IDENTITY
	var collision := CollisionShape3D.new()
	collision.shape = shape
	body.add_child(collision)
	collider_count += 1


func bake(nest: Node3D) -> NavigationRegion3D:
	if not _authoring and _complete_estate:
		if _spatial_data==null:
			push_error("Cannot load navigation without compiled estate spatial resources")
			return null
		var cached := _spatial_data.navigation_scene.instantiate() as NavigationRegion3D
		var map := nest.get_world_3d().navigation_map
		NavigationServer3D.map_set_cell_size(map,cached.navigation_mesh.cell_size)
		NavigationServer3D.map_set_cell_height(map,cached.navigation_mesh.cell_height)
		nest.add_child(cached)
		print("ESTATE_NAVIGATION_LOADED polygons=",cached.navigation_mesh.get_polygon_count())
		return cached
	var region := NavigationRegion3D.new()
	region.name = "RuntimeNavigation"
	var nav := NavigationMesh.new()
	# Both species use a 1.72 x .34 capsule scaled by .7. Include appearance
	# limits (height 1.18, build 1.15) and recovery/grid clearance: maximum
	# physical height 1.421 m, radius .274 m, not the retired room agent.
	for setting: String in SPATIAL.NAV_SETTINGS:nav.set(setting,SPATIAL.NAV_SETTINGS[setting])
	nav.filter_baking_aabb = AABB(Vector3(-51, -0.12, -45), Vector3(102, 14, 102))
	nav.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	nav.geometry_collision_mask = LAYERS.NAVIGATION_MASK
	nav.geometry_source_geometry_mode = NavigationMesh.SOURCE_GEOMETRY_GROUPS_WITH_CHILDREN
	nav.geometry_source_group_name = SOURCE_GROUP
	var map := nest.get_world_3d().navigation_map
	NavigationServer3D.map_set_cell_size(map, nav.cell_size)
	NavigationServer3D.map_set_cell_height(map, nav.cell_height)
	region.navigation_mesh = nav
	nest.add_child(region)
	if outdoor_access != null:
		var geometry := NavigationMeshSourceGeometryData3D.new()
		NavigationServer3D.parse_source_geometry_data(nav,geometry,nest)
		outdoor_access.restrict_navigation(geometry,nav.filter_baking_aabb)
		NavigationServer3D.bake_from_source_geometry_data(nav,geometry)
		outdoor_access.retain_reachable_navigation(nav)
	else:
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
