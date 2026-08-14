extends SceneTree

const REQUIRED_RESOURCES := [
	"res://main.tscn",
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
	"res://characters/dog/dog.tscn",
	"res://characters/fox/fox.tscn",
	"res://characters/cat/cat.tscn",
	"res://characters/shared/elfie_actor.gd",
	"res://lab_preview_controller.gd",
	"res://runtime/actor/actor_controller.gd",
	"res://runtime/world/world_controller.gd",
	"res://runtime/endpoint/runtime_mode.gd",
	"res://runtime/endpoint/authority_semantic_events.gd",
	"res://runtime/lab/lab_runtime.gd",
	"res://scripts/test/test_runtime_mode_contract.gd",
	"res://scripts/test/test_authority_semantic_replay.gd",
	"res://scripts/test/test_runtime_actor_catalog.gd",
	"res://scripts/test/test_cat_scene_contract.gd",
	"res://scripts/test/test_runtime_navigation.gd",
	"res://scripts/test/test_runtime_interaction.gd",
	"res://scripts/test/test_runtime_scene_manifest.gd",
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
	if main_instance.get_script() == null:
		main_instance.free()
		push_error("Main scene root script could not be loaded")
		quit(1)
		return
	var nest := main_instance.get_node_or_null("Nest")
	var characters := main_instance.get_node_or_null("Characters")
	if (
		nest == null
		or characters == null
		or characters.get_child_count() != 0
	):
		main_instance.free()
		push_error(
		"Main scene must contain Nest and an empty Characters container"
		)
		quit(1)
		return
	main_instance.free()

	print("Scene resource contract passed")
	quit()
