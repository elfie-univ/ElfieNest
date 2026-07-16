extends SceneTree

const REQUIRED_RESOURCES := [
	"res://main.tscn",
	"res://camera_stream_bridge.gd",
	"res://rooms/nest.tscn",
	"res://rooms/activity_room.tscn",
	"res://rooms/dorm_room.tscn",
	"res://rooms/portal_room.tscn",
	"res://ui/observation_hud.tscn",
	"res://rooms/common_area_layouts/kitchen_layout.tscn",
	"res://rooms/common_area_layouts/sitting_layout.tscn",
	"res://rooms/common_area_layouts/media_layout.tscn",
	"res://rooms/common_area_layouts/gym_layout.tscn",
	"res://rooms/common_area_layouts/garden_layout.tscn",
	"res://rooms/common_area_layouts/working_layout.tscn",
	"res://rooms/common_area_layouts/music_layout.tscn",
	"res://rooms/common_area_layouts/bookroom_layout.tscn",
	"res://characters/elfie/elfie_3d.tscn",
]


func _init() -> void:
	var missing: Array[String] = []
	for resource_path: String in REQUIRED_RESOURCES:
		if not ResourceLoader.exists(resource_path):
			missing.append(resource_path)

	if not missing.is_empty():
		push_error("Missing required resources: %s" % [missing])
		quit(1)
		return

	var main_scene := load("res://main.tscn") as PackedScene
	if main_scene == null:
		push_error("Main scene could not be loaded")
		quit(1)
		return

	var main_instance := main_scene.instantiate()
	var nest := main_instance.get_node_or_null("Nest")
	var characters := main_instance.get_node_or_null("Characters")
	var camera_bridge := main_instance.get_node_or_null("CameraStreamBridge")
	if (
		nest == null
		or characters == null
		or characters.get_child_count() != 0
		or camera_bridge == null
	):
		main_instance.free()
		push_error(
			"Main scene must contain Nest, CameraStreamBridge, and an empty Characters container"
		)
		quit(1)
		return
	main_instance.free()

	print("Scene resource contract passed")
	quit()
