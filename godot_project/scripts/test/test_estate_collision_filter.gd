extends SceneTree

const PHYSICS := preload("res://rooms/estate/estate_physics.gd")


func _init() -> void:
	call_deferred("run")


func run() -> void:
	for source: String in ["STAIR • solid flight 0", "STAIR • solid flight 1", "ROOM • sculpted continuous shell"]:
		var mesh := MeshInstance3D.new()
		mesh.set_meta("extras", {"module": "M01", "source_name": source})
		var included := PHYSICS.uses_concave_collision(mesh)
		mesh.free()
		if not included:
			push_error("Structural collision was mistaken for lighting: " + source)
			quit(1)
			return
	for source: String in ["ROOM • closed ceiling light", "ROOM • five-petal solid opal ceiling lamp"]:
		var mesh := MeshInstance3D.new()
		mesh.set_meta("extras", {"module": "M01", "source_name": source})
		var included := PHYSICS.uses_concave_collision(mesh)
		mesh.free()
		if included:
			push_error("Decorative light was included in structural collisions: " + source)
			quit(1)
			return
	var hidden_estate := Node3D.new()
	hidden_estate.visible = false
	root.add_child(hidden_estate)
	var physical_floor := MeshInstance3D.new()
	physical_floor.mesh = BoxMesh.new()
	if PHYSICS.collision_faces(physical_floor.mesh).to_byte_array() != physical_floor.mesh.get_faces().to_byte_array():
		push_error("Direct collision triangles differ from the original indexed mesh")
		quit(1)
		return
	physical_floor.set_meta("extras", {"module": "M01", "source_name": "ROOM • continuous lower floor"})
	hidden_estate.add_child(physical_floor)
	var physics := PHYSICS.new()
	var material_variant := MeshInstance3D.new()
	material_variant.mesh = BoxMesh.new()
	material_variant.material_override = StandardMaterial3D.new()
	material_variant.position.x = 2.0
	material_variant.set_meta("extras", {"module": "M02", "source_name": "ROOM • continuous lower floor"})
	hidden_estate.add_child(material_variant)
	root.add_child(physics)
	physics.build(hidden_estate)
	if physics.collider_count != 2:
		push_error("Hidden/headless presentation erased the physical world")
		quit(1)
		return
	if physics.get("_shapes").size() != 1:
		push_error("Identical collision geometry was duplicated because render materials differ")
		quit(1)
		return
	hidden_estate.queue_free()
	physics.queue_free()
	await process_frame
	var furniture := Node3D.new()
	root.add_child(furniture)
	for source: String in ["Coffee table high round softened oak top", "Floor plant | rounded ceramic planter", "Botanical V1 front fern ivory pot"]:
		var mesh := MeshInstance3D.new()
		mesh.mesh = BoxMesh.new()
		mesh.set_meta("extras", {"module": "central", "source_name": source, "furniture": true})
		furniture.add_child(mesh)
	var furniture_physics := PHYSICS.new()
	root.add_child(furniture_physics)
	furniture_physics.build(furniture)
	if furniture_physics.collider_count != 3:
		push_error("Untagged coffee tables and solid planters have no collision")
		quit(1)
		return
	furniture.queue_free()
	furniture_physics.queue_free()
	await process_frame
	if not _test_authored_sliding_door():
		return
	print("PASS collision classification: both stair flights retained, lamps excluded, hidden authority collides")
	quit(0)


func _test_authored_sliding_door() -> bool:
	var estate := Node3D.new()
	root.add_child(estate)
	var leaf := MeshInstance3D.new()
	leaf.mesh = BoxMesh.new()
	leaf.position = Vector3(10.0, 1.2, 0.0)
	leaf.set_meta("extras", {"module": "M01", "door_leaf": true, "slideAxis": [1, 0, 0], "slideTravelM": 1.75})
	estate.add_child(leaf)
	var physics := PHYSICS.new()
	root.add_child(physics)
	physics.build(estate)
	var bodies := physics.find_children("*", "StaticBody3D", true, false)
	if bodies.size() != 1:
		push_error("Authored sliding door has no unique physical body")
		quit(1)
		return false
	var body := bodies[0] as Node3D
	var closed := leaf.global_transform
	var actor := Node3D.new()
	root.add_child(actor)
	actor.add_to_group(&"runtime_elfie_actors")
	actor.global_position = Vector3(10.0, 0.0, 0.0)
	physics._physics_process(0.4)
	if not leaf.global_position.is_equal_approx(closed.origin + Vector3(1.75, 0.0, 0.0)) or not body.global_transform.is_equal_approx(leaf.global_transform):
		push_error("Nearby actor did not open the authored door and its collision together")
		quit(1)
		return false
	actor.global_position = Vector3(100.0, 0.0, 0.0)
	physics._physics_process(0.4)
	if not leaf.global_transform.is_equal_approx(closed) or not body.global_transform.is_equal_approx(closed):
		push_error("Authored door and collision did not close after the actor left")
		quit(1)
		return false
	actor.free()
	physics.free()
	estate.free()
	return true
