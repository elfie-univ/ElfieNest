extends SceneTree

var _start := Time.get_ticks_msec()


func _init() -> void:
	call_deferred("_profile")


func _profile() -> void:
	var final_scene := load("res://rooms/estate/estate.tscn") as PackedScene
	var estate := final_scene.instantiate() as Node3D
	root.add_child(estate)
	await process_frame
	_checkpoint("complete_final")
	var bodies := estate.find_children("*", "StaticBody3D", true, false)
	var meshes := estate.find_children("*", "MeshInstance3D", true, false)
	var metadata_examples: Array = []
	for node in meshes:
		if metadata_examples.size() < 4 and node.name.contains("Central"):
			var metadata := {}
			for key in node.get_meta_list():
				metadata[key] = node.get_meta(key)
			metadata_examples.append({"name": str(node.name), "metadata": metadata, "aabb": str(node.get_aabb()), "transform": str(node.global_transform)})
	print("ESTATE_STRUCTURE ", JSON.stringify({"static_bodies": bodies.size(), "mesh_nodes": meshes.size(), "metadata_examples": metadata_examples}))
	estate.queue_free()
	await process_frame
	var nest_scene := load("res://rooms/nest.tscn") as PackedScene
	var nest := nest_scene.instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	_checkpoint("complete_nest_with_observer")
	if nest.observation_view_count() != 15:
		push_error("Complete estate observer camera catalog is incomplete")
		quit(1)
		return
	nest.queue_free()
	await process_frame
	quit(0)


func _checkpoint(stage: String) -> void:
	var output: Array = []
	OS.execute("/bin/ps", PackedStringArray(["-o", "rss=", "-p", str(OS.get_process_id())]), output)
	print("ESTATE_PROFILE ", JSON.stringify({"stage": stage, "elapsed_ms": Time.get_ticks_msec() - _start, "static_bytes": OS.get_static_memory_usage(), "rss_kib": str(output[0]).strip_edges().to_int()}))
