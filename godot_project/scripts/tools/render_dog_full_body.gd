extends SceneTree

const OUTPUT_PATH := "res://../build/dog-full-body.png"
const IMAGE_SIZE := Vector2i(512, 512)


func _init() -> void:
	call_deferred("_render")


func _render() -> void:
	var viewport := SubViewport.new()
	viewport.size = IMAGE_SIZE
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.transparent_bg = false
	root.add_child(viewport)

	var world_root := Node3D.new()
	viewport.add_child(world_root)
	var environment := WorldEnvironment.new()
	var environment_resource := Environment.new()
	environment_resource.background_mode = Environment.BG_COLOR
	environment_resource.background_color = Color("b7cbd3")
	environment_resource.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment_resource.ambient_light_color = Color("e4eef2")
	environment_resource.ambient_light_energy = 0.78
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
	camera.position = Vector3(0.0, 0.96, 3.85)
	camera.fov = 36.0
	world_root.add_child(camera)
	camera.look_at(Vector3(0.0, 0.88, 0.0), Vector3.UP)
	camera.current = true

	var actor_scene := load("res://characters/dog/dog.tscn") as PackedScene
	var actor := actor_scene.instantiate() as ElfieActor
	actor.install_shared_animations = false
	world_root.add_child(actor)
	actor.configure("dog-presentation", Vector3.ZERO, {})
	actor.set_physics_process(false)

	await process_frame
	await process_frame
	await process_frame
	var image := viewport.get_texture().get_image()
	var absolute_path := ProjectSettings.globalize_path(OUTPUT_PATH)
	DirAccess.make_dir_recursive_absolute(absolute_path.get_base_dir())
	var error := image.save_png(absolute_path)
	viewport.queue_free()
	if error != OK:
		push_error("Could not save dog portrait: %s" % error)
		quit(1)
		return
	print("Saved dog full-body portrait: ", absolute_path)
	quit()
