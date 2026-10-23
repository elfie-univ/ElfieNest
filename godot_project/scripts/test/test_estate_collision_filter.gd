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
	print("PASS collision classification: both stair flights retained, lamps excluded, hidden authority collides")
	quit(0)
