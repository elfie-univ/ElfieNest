extends SceneTree

const OUTPUT_PATH := "res://../build/fox_bone_proportion_comparison.png"
const TILE_SIZE := Vector2i(400, 450)
const VARIANTS := [
	{"label": "ARM 0.65 (short)", "control": "ArmLength", "factor": 0.65},
	{"label": "ARM 1.35 (long)", "control": "ArmLength", "factor": 1.35},
	{"label": "LEG 0.65 (short)", "control": "LegLength", "factor": 0.65},
	{"label": "LEG 1.35 (long)", "control": "LegLength", "factor": 1.35},
	{"label": "NECK 0.50 (short)", "control": "NeckLength", "factor": 0.50},
	{"label": "NECK 1.50 (long)", "control": "NeckLength", "factor": 1.50},
	{"label": "HEAD 0.65 (small)", "control": "HeadScale", "factor": 0.65},
	{"label": "HEAD 1.35 (large)", "control": "HeadScale", "factor": 1.35},
]


func _init() -> void:
	call_deferred("_render_comparison")


func _render_comparison() -> void:
	var output := Image.create_empty(TILE_SIZE.x * 4, TILE_SIZE.y * 2, false, Image.FORMAT_RGBA8)
	for index in range(VARIANTS.size()):
		var tile := await _render_variant(VARIANTS[index])
		if tile == null or tile.is_empty():
			push_error("Renderer returned an empty image for variant %s" % index)
			quit(1)
			return
		output.blit_rect(
			tile,
			Rect2i(Vector2i.ZERO, TILE_SIZE),
			Vector2i((index % 4) * TILE_SIZE.x, (index / 4) * TILE_SIZE.y),
		)
	var absolute_path := ProjectSettings.globalize_path(OUTPUT_PATH)
	DirAccess.make_dir_recursive_absolute(absolute_path.get_base_dir())
	var error := output.save_png(absolute_path)
	if error != OK:
		push_error("Could not save comparison image: %s" % error)
		quit(1)
		return
	print("Saved bone proportion comparison: ", absolute_path)
	quit()


func _render_variant(variant: Dictionary) -> Image:
	var viewport := SubViewport.new()
	viewport.size = TILE_SIZE
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.transparent_bg = false
	root.add_child(viewport)

	var world_root := Node3D.new()
	viewport.add_child(world_root)
	var environment := WorldEnvironment.new()
	var environment_resource := Environment.new()
	environment_resource.background_mode = Environment.BG_COLOR
	environment_resource.background_color = Color("24282d")
	environment_resource.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment_resource.ambient_light_color = Color("dbe7ee")
	environment_resource.ambient_light_energy = 0.72
	environment.environment = environment_resource
	world_root.add_child(environment)

	var key_light := DirectionalLight3D.new()
	key_light.rotation_degrees = Vector3(-32.0, -28.0, 0.0)
	key_light.light_energy = 1.25
	key_light.shadow_enabled = true
	world_root.add_child(key_light)
	var fill_light := DirectionalLight3D.new()
	fill_light.rotation_degrees = Vector3(-18.0, 145.0, 0.0)
	fill_light.light_energy = 0.55
	world_root.add_child(fill_light)

	var camera := Camera3D.new()
	camera.position = Vector3(0.0, 0.95, 3.85)
	camera.fov = 36.0
	world_root.add_child(camera)
	camera.look_at(Vector3(0.0, 0.88, 0.0), Vector3.UP)
	camera.current = true

	var actor_scene := load("res://characters/fox/fox.tscn") as PackedScene
	var actor := actor_scene.instantiate() as ElfieActor
	actor.install_shared_animations = false
	world_root.add_child(actor)
	actor.configure(
		"comparison",
		Vector3.ZERO,
		{
			"height_scale": 1.0,
			"build_scale": 1.0,
			"bone_scales": {variant["control"]: variant["factor"]},
		},
	)
	actor.set_physics_process(false)

	var label := Label.new()
	label.text = variant["label"]
	label.position = Vector2(14.0, 12.0)
	label.add_theme_font_size_override("font_size", 24)
	label.add_theme_color_override("font_color", Color.WHITE)
	label.add_theme_color_override("font_shadow_color", Color(0.0, 0.0, 0.0, 0.85))
	label.add_theme_constant_override("shadow_offset_x", 2)
	label.add_theme_constant_override("shadow_offset_y", 2)
	viewport.add_child(label)

	await process_frame
	await process_frame
	await process_frame
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image
