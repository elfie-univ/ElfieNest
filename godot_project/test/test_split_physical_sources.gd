extends SceneTree

class PlacementData extends Node3D:
	var instance_batches: Dictionary = {}

class OpenGround extends Node3D:
	func contains_outdoor_point(_point: Vector2) -> bool: return true

func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok

func run() -> void:
	var estate := Node3D.new()
	estate.set_meta("activity_regions", preload("res://nest/assembly/activity_regions.gd").new())
	root.add_child(estate)
	var ground := MeshInstance3D.new()
	ground.mesh = BoxMesh.new()
	ground.mesh.set_meta("nest_source_extras", {"source_name": "COMPLETE Building garden island"})
	estate.add_child(ground)
	var placements := PlacementData.new()
	estate.add_child(placements)
	var tree := MultiMeshInstance3D.new()
	tree.multimesh = MultiMesh.new()
	tree.multimesh.transform_format = MultiMesh.TRANSFORM_3D
	tree.multimesh.mesh = BoxMesh.new()
	tree.multimesh.mesh.set_meta("nest_source_library", "res://nest/courtyard/parts/forest/forest-wood.glb")
	tree.multimesh.instance_count = 2
	# Deliberately leave renderer transforms at identity; only canonical data is valid.
	placements.instance_batches[0] = {"transform_format": MultiMesh.TRANSFORM_3D, "instance_count": 2, "use_colors": false, "use_custom_data": false, "buffer": PackedFloat32Array([1,0,0,10,0,1,0,0,0,0,1,-10, 1,0,0,-10,0,1,0,0,0,0,1,10])}
	placements.add_child(tree)
	var physics := preload("res://nest/estate/estate_physics.gd").new()
	root.add_child(physics)
	preload("res://nest/assembly/physical_sources.gd").build(estate, null, physics)
	var body := estate.get_node("LandscapePhysics/GardenCollision_TreeTrunks") as StaticBody3D
	var first := body.get_child(0) as CollisionShape3D
	var second := body.get_child(1) as CollisionShape3D
	if not require(first.shape == second.shape, "Landscape instances must share collision geometry"): return
	if not require(first.global_position == Vector3(10,0,-10) and second.global_position == Vector3(-10,0,10), "Physics must use canonical placements, never renderer readback"): return
	physics._static = Node3D.new()
	physics.add_child(physics._static)
	physics.outdoor_access = OpenGround.new()
	physics.add_child(physics.outdoor_access)
	physics._retain_accessible_obstacle(body)
	if not require(physics._static.get_child_count() == 1, "Both real tree placements must contribute accessible collision"): return
	var retained: PackedVector3Array = physics._static.get_child(0).get_child(0).shape.get_faces()
	var left := false
	var right := false
	for point: Vector3 in retained:
		if point.x < -9: left = true
		if point.x > 9: right = true
	if not require(left and right, "Height-indexed clipping must retain both original collision placements"): return
	print("PASS split collision: canonical matrices and shared shapes; renderer identity cannot move trees")
	physics.free(); estate.free(); quit()
