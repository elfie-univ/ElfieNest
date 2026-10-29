extends Node3D
## Connected review route cut from the original estate at original transforms.
## Rendering/physics changes here belong only to this explicit local audition.

const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
var geometry: Node3D
var physics: Node3D
var semantics: RefCounted
var seats: Array[Dictionary] = []


func build() -> bool:
	geometry = Node3D.new()
	add_child(geometry)
	var source := (load("res://rooms/estate/ElfieNest-complete-final.glb") as PackedScene).instantiate()
	source.visible = false
	add_child(source)
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var e := mesh.get_meta("extras", {}) as Dictionary
		if e.get("module", "") not in ["central", "M01", "M07"]: continue
		if PHYSICS.is_instancing_template(mesh): continue
		mesh.reparent(geometry, true)
		mesh.visible = true
	source.free()
	preload("res://rooms/estate/estate_daylight.gd").apply(geometry)
	physics = PHYSICS.new()
	add_child(physics)
	physics.build(geometry)
	configure_sofa_collision(geometry,physics)
	semantics = preload("res://rooms/estate/estate_semantics.gd").new()
	semantics.build(self, geometry)
	physics.bake(self)
	var map := get_world_3d().navigation_map
	for frame in range(120):
		await get_tree().physics_frame
		if NavigationServer3D.map_get_iteration_id(map) > 0: break
	NavigationServer3D.map_force_update(map)
	var synced := false
	for frame in range(120):
		await get_tree().physics_frame
		var nearest := NavigationServer3D.map_get_closest_point(map, Vector3(1.4, 0.32, 0.38))
		if not nearest.is_zero_approx() and absf(nearest.y - 0.3) < 0.16:
			synced = true
			break
	if not synced: return false
	semantics.align_approaches(map)
	return bind_seats()


static func configure_sofa_collision(geometry: Node3D, physics: Node3D) -> void:
	# Integrated sofa/back meshes are concave: preserve the actual sitting
	# recess instead of the filled space of their single convex hull.
	for body: StaticBody3D in physics.find_children("*", "StaticBody3D", true, false):
		var mesh := geometry.find_child(String(body.get_meta("source_node", "")), true, false) as MeshInstance3D
		if mesh == null: continue
		var e := mesh.get_meta("extras", {}) as Dictionary
		if e.get("kind") != "sofa" and String(mesh.name) not in ["Soft V2 continuous sculpted back and integrated arms", "Soft V2 single rounded upholstered body"]: continue
		var shape := ConcavePolygonShape3D.new()
		shape.set_faces(PHYSICS.collision_faces(mesh.mesh))
		shape.backface_collision = true
		(body.get_child(0) as CollisionShape3D).shape = shape


func bind_existing(nest: Node3D) -> bool:
	geometry = nest.get_node("Generated/CompleteEstate")
	physics = nest.get("_estate_physics")
	semantics = nest.get("_estate_semantics")
	return bind_seats()


func bind_seats() -> bool:
	seats.clear()
	var cushion := _find("central", "Upholstery V3 fitted full-depth seat cushion 1")
	if cushion == null: return false
	var bounds := cushion.global_transform * cushion.get_aabb()
	seats.append({"id": "F08", "label": "Central lounge", "contact": Transform3D(Basis.IDENTITY, Vector3(bounds.get_center().x, bounds.end.y, bounds.end.z - 0.08)), "floor_y": 0.3})
	# Per-seat contact annotations, measured on original seat surfaces. These
	# are furniture inputs, not copied animation files or relocated furniture.
	if not _terrace_seat("F10", "Cinema terrace M01", "M01", "sofa_following_actual_wall", Vector3(-1.1, 3.705, 1.70), Vector3(0, 0, -1)): return false
	if not _terrace_seat("F13", "Tea terrace M07", "M07", "left_wall_fitted_tea_sofa", Vector3(-1.72, 3.705, 1.39), Vector3(0.403, 0, -0.915)): return false
	for seat: Dictionary in seats:
		print("TOUR_SEAT ", seat["id"], " contact=", seat["contact"], " floor=", seat["floor_y"])
	return true


func _find(module: String, name: String) -> MeshInstance3D:
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var e := mesh.get_meta("extras", {}) as Dictionary
		if e.get("module") == module and String(e.get("source_name", mesh.name)) == name: return mesh
	return null


func _terrace_seat(id: String, label: String, module: String, name: String, local: Vector3, front: Vector3) -> bool:
	var mesh := _find(module, name)
	if mesh == null: return false
	var contact := mesh.to_global(local)
	var direction := (mesh.global_basis * front).normalized()
	direction.y = 0
	var basis := Basis(Vector3.UP, atan2(direction.x, direction.z))
	var floor := _find(module, "ROOM • inset terrace walking finish")
	if floor == null: return false
	var floor_y := (floor.global_transform * floor.get_aabb()).end.y
	seats.append({"id": id, "label": label, "contact": Transform3D(basis, contact), "floor_y": floor_y})
	return true
