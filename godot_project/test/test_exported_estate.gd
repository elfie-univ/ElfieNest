extends SceneTree


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var pack := ProjectSettings.globalize_path("res://../build/components/godot-web/elfienest.pck")
	if not ProjectSettings.load_resource_pack(pack):
		push_error("Cannot mount the actual exported Web resource pack")
		quit(1)
		return
	var scene := load("res://nest/assembly/estate.tscn") as PackedScene
	if scene == null:
		push_error("Exported estate scene is missing")
		quit(1)
		return
	var estate := scene.instantiate()
	root.add_child(estate)
	await process_frame
	var error := preload("res://test/split_estate_test_support.gd").batch_error(estate)
	if not bool(estate.get_meta("split_runtime_ready", false)) or not error.is_empty():
		push_error("Exported split estate did not bind its canonical instances: " + error)
		quit(1)
		return
	print("PASS: actual exported estate instantiates and restores its authored instances")
	quit(0)
