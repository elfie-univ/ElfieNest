extends SceneTree

const NEST_SCENE := preload("res://rooms/nest.tscn")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var nest := NEST_SCENE.instantiate() as ModularNest
	nest.show_observation_hud = false
	root.add_child(nest)
	await process_frame
	await process_frame
	var estate := nest.get_node("Generated/CompleteEstate")
	if not String(estate.get("restore_error")).is_empty():
		push_error("Complete estate restoration failed")
		quit(1)
		return
	# Imported meshes may combine furniture and architecture. Report source bounds;
	# mesh AABB overlap alone cannot certify furniture clearance in the new asset.
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if not mesh.is_visible_in_tree():
			continue
		var extras := mesh.get_meta("extras", {}) as Dictionary
		var bounds := mesh.global_transform * mesh.get_aabb()
		print("SIZE\t%s\t%s\t%s\t%s" % [
			String(extras.get("module", "")),
			String(extras.get("source_name", mesh.name)),
			bounds.size,
			bounds.position,
		])
	print("Complete estate bounds inventory only; furniture clearance requires asset review")
	quit(0)
