extends SceneTree


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var pack := ProjectSettings.globalize_path("res://../build/components/godot-web/elfienest.pck")
	if not ProjectSettings.load_resource_pack(pack):
		push_error("Cannot mount the actual exported Web resource pack")
		quit(1)
		return
	var scene := load("res://rooms/estate/estate.tscn") as PackedScene
	if scene == null:
		push_error("Exported estate scene is missing")
		quit(1)
		return
	var estate := scene.instantiate()
	var model := estate.get_node_or_null("CompleteFinal")
	if not model is Node3D or model.find_child("__ELFIE_INST_GROUP_000", true, false) == null:
		estate.free()
		push_error("Exported estate lost its model type or authored instance markers")
		quit(1)
		return
	root.add_child(estate)
	await process_frame
	if not str(estate.get("restore_error")).is_empty():
		push_error("Exported estate failed to restore its real instances")
		quit(1)
		return
	print("PASS: actual exported estate instantiates and restores its authored instances")
	quit(0)
