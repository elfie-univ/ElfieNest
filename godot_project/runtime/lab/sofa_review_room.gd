extends Node3D
## Original central ground floor, original sofa and physical surroundings.

const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
var geometry: Node3D
var physics: Node3D
var cushion: MeshInstance3D
var floor_mesh: MeshInstance3D
var contact := Transform3D.IDENTITY
var floor_y := 0.0


func build() -> Dictionary:
	geometry = Node3D.new()
	add_child(geometry)
	var source := (load("res://rooms/estate/ElfieNest-complete-final.glb") as PackedScene).instantiate()
	source.visible = false
	add_child(source)
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("module") != "central" or int(e.get("floor", 0)) != 1: continue
		mesh.reparent(geometry, true)
		mesh.visible = true
		if String(mesh.name) == "Upholstery V3 fitted full-depth seat cushion 1": cushion = mesh
		if String(mesh.name) == "Central L1 fitted complete floor": floor_mesh = mesh
	source.free()
	if cushion == null or floor_mesh == null: return {"ready": false}
	preload("res://rooms/estate/estate_daylight.gd").apply(geometry)
	physics = PHYSICS.new()
	add_child(physics)
	physics.build(geometry)
	# One convex hull across the integrated U-shaped back fills the usable
	# sitting recess. For this fixture use the original back's real surface.
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		if String(mesh.name) not in ["Soft V2 continuous sculpted back and integrated arms", "Soft V2 single rounded upholstered body"]: continue
		for body: StaticBody3D in physics.find_children("*", "StaticBody3D", true, false):
			if String(body.get_meta("source_node", "")) != String(mesh.name): continue
			var shape := ConcavePolygonShape3D.new()
			shape.set_faces(PHYSICS.collision_faces(mesh.mesh))
			shape.backface_collision = true
			(body.get_child(0) as CollisionShape3D).shape = shape
	var navigation: NavigationRegion3D = physics.bake(self)
	var map := get_world_3d().navigation_map
	for frame in range(20):
		await get_tree().physics_frame
		if NavigationServer3D.map_get_iteration_id(map) > 0: break
	NavigationServer3D.map_force_update(map)
	floor_y = (floor_mesh.global_transform * floor_mesh.get_aabb()).end.y
	var bounds := cushion.global_transform * cushion.get_aabb()
	# Middle cushion, open front (+Z), ahead of the separate rear pillows.
	contact.origin = Vector3(bounds.get_center().x, bounds.end.y, bounds.end.z - 0.08)
	# An iteration counter alone can refer to the empty map before this region
	# was uploaded. Wait for a real query in this fixture's floor, not elapsed time.
	var ready := false
	var floor_query := contact.origin + Vector3(1.8, 0, 1.9)
	floor_query.y = floor_y + 0.02
	for frame in range(120):
		await get_tree().physics_frame
		var nearest := NavigationServer3D.map_get_closest_point(map, floor_query)
		if not nearest.is_zero_approx() and absf(nearest.y - floor_y) < 0.2:
			ready = true
			break
	print("SOFA_ORIGINAL_GEOMETRY seat=", contact.origin, " floor_y=", floor_y, " height=", contact.origin.y - floor_y, " meshes=", geometry.get_child_count())
	print("SOFA_MAP ready=", ready, " regions=", NavigationServer3D.map_get_regions(map).size(), " iteration=", NavigationServer3D.map_get_iteration_id(map))
	return {"ready": ready and navigation.navigation_mesh.get_polygon_count() > 0}
