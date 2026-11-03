extends SceneTree

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var door := preload("res://rooms/estate/estate_door.gd").new({})
	assert(door.set_preview_mode("open"))
	assert(door.preview_mode == "open")
	assert(not door.set_preview_mode("invalid"))
	assert(door.set_preview_mode("auto"))
	assert(door.preview_mode == "auto")
	print("PASS action preview door modes")
	quit()
