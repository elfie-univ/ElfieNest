extends SceneTree
func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok
func run() -> void:
	create_timer(60.0).timeout.connect(func(): push_error("Observer memory verification timed out");quit(1))
	var before := OS.get_static_memory_usage()
	var nest := load("res://rooms/nest.tscn").instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	nest.apply_observer_environment({"phase":"night","lights_on":true,"quiet_mode":false})
	var bytes := OS.get_static_memory_usage()-before
	print("OBSERVER_MEMORY bytes=",bytes)
	if not require(bytes<1600000000,"Complete observer must stay below 1.6 GB of scene allocations"):return
	var estate := nest.get_node("Generated/CompleteEstate") as CompleteEstateFinal
	if not require(estate.multimesh_group_count==134 and estate.multimesh_instance_count==214448,"Every landscape group and instance must remain present"):return
	if not require(estate.find_children("*","MeshInstance3D",true,false).size()>=9000,"Complete building and furniture geometry must remain present"):return
	if not require(nest.semantic_anchor_ids().size()==87 and nest._estate_physics.collider_count==1257 and nest._estate_physics._doors.size()==10,"Complete interaction and physics must remain present"):return
	if not require(nest.bake_navigation() and await nest.wait_for_navigation_sync() and nest.validate_navigation_anchors(),"Every anchor must retain its complete route to the courtyard"):return
	print("PASS complete observer memory: all models, instances, collisions, doors and navigation retained")
	nest.free()
	quit()
