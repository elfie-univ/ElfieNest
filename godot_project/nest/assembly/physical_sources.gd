extends RefCounted
## Physical sources use the same split meshes and share shapes between instances.
const LAYERS := preload("res://runtime/world/collision_layers.gd")
const GROUPS := ["GardenCollision_Hardscape", "GardenCollision_TreeTrunks", "GardenCollision_ShoreRocks", "GardenCollision_Furniture"]

static func build(estate: Node3D, cached: Resource, physics: Node3D) -> void:
	if cached != null:
		install_hardscape(estate, cached.hardscape_shape)
		var background: Node3D = cached.background_scene.instantiate()
		estate.add_child(background)
		return
	var background := Node3D.new()
	background.name = "LandscapePhysics"
	estate.add_child(background)
	var bodies := {}
	for key: String in GROUPS.slice(1):
		var body := StaticBody3D.new()
		body.name = key
		body.collision_layer = LAYERS.PERCEPTION_ONLY
		background.add_child(body)
		body.global_transform = Transform3D.IDENTITY
		bodies[key] = body
	var hardscape := PackedVector3Array()
	var activity: Resource = estate.get_meta("activity_regions")
	var prototypes := {}
	var shapes := {}
	for node: Node3D in estate.find_children("*", "Node3D", true, false):
		if node.has_meta("source_geometry_path"): continue
		var mesh: Mesh
		if node is MeshInstance3D: mesh = node.mesh
		elif node is MultiMeshInstance3D and node.multimesh != null: mesh = node.multimesh.mesh
		if mesh == null: continue
		var library := str(mesh.get_meta("nest_source_library", "")).get_file()
		var group := ""
		if library == "forest-wood.glb": group = GROUPS[1]
		elif library == "shore-stones.glb": group = GROUPS[2]
		elif node is MeshInstance3D:
			var source: String = activity.source_name(node)
			if activity.zone_for(node) in ["lawn", "courtyard"] or source in ["Preview 0_8m solid stone boundary", "Preview shallow limestone wall cap", "Continuous boundary base rim"]: group = GROUPS[0]
			elif source.begins_with("Picnic ") or source.begins_with("Lakeside ") or source.begins_with("Swing "): group = GROUPS[3]
		if group.is_empty(): continue
		var id := mesh.get_instance_id()
		if not prototypes.has(id): prototypes[id] = physics.collision_faces(mesh)
		var faces: PackedVector3Array = prototypes[id]
		if group == GROUPS[0]:
			for vertex: Vector3 in faces: hardscape.append(node.global_transform * vertex)
			continue
		if not shapes.has(id):
			var shape := ConcavePolygonShape3D.new()
			shape.set_faces(faces)
			shape.backface_collision = true
			shapes[id] = shape
		if node is MultiMeshInstance3D:
			# Renderer readback is not authoring data (dummy/headless returns identity).
			var data: Dictionary = node.get_parent().instance_batches[node.get_index()]
			assert(data.transform_format == MultiMesh.TRANSFORM_3D)
			var buffer: PackedFloat32Array = data.buffer
			var stride := 12 + (4 if data.use_colors else 0) + (4 if data.use_custom_data else 0)
			assert(buffer.size() == data.instance_count * stride)
			for index: int in data.instance_count:
				var at := index * stride
				var placed := Transform3D(Basis(Vector3(buffer[at], buffer[at+4], buffer[at+8]), Vector3(buffer[at+1], buffer[at+5], buffer[at+9]), Vector3(buffer[at+2], buffer[at+6], buffer[at+10])), Vector3(buffer[at+3], buffer[at+7], buffer[at+11]))
				install_instance(bodies[group], shapes[id], node.global_transform * placed, mesh.get_aabb())
		else: install_instance(bodies[group], shapes[id], node.global_transform, mesh.get_aabb())
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(hardscape)
	shape.backface_collision = true
	install_hardscape(estate, shape)
	print("SPLIT_PHYSICAL_SOURCE shared_landscape_shapes=", shapes.size(), " hardscape_triangles=", hardscape.size() / 3)

static func install_instance(body: StaticBody3D, shape: Shape3D, frame: Transform3D, bounds: AABB) -> void:
	var collision := CollisionShape3D.new()
	collision.shape = shape
	collision.set_meta("source_bounds", bounds)
	body.add_child(collision)
	collision.global_transform = frame

static func install_hardscape(estate: Node3D, shape: Shape3D) -> void:
	var body := StaticBody3D.new()
	body.name = GROUPS[0]
	body.collision_layer = LAYERS.WORLD_SOLIDS
	estate.add_child(body)
	body.global_transform = Transform3D.IDENTITY
	var collision := CollisionShape3D.new()
	collision.shape = shape
	body.add_child(collision)
