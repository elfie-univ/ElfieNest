# Render two static candidate photos without starting the Nest authority.

extends SceneTree

const FULL_SIZE := Vector2i(512, 768)
const HEAD_SIZE := Vector2i(512, 512)

var _input_path := ""
var _output_dir := ""


func _init() -> void:
	var arguments := OS.get_cmdline_user_args()
	for index in range(arguments.size()):
		if arguments[index] == "--input" and index + 1 < arguments.size():
			_input_path = arguments[index + 1]
		if arguments[index] == "--output-dir" and index + 1 < arguments.size():
			_output_dir = arguments[index + 1]
	if _input_path.is_empty() or _output_dir.is_empty():
		push_error("render_adoption_portraits requires --input and --output-dir")
		quit(2)
		return
	call_deferred("_render")


func _render() -> void:
	var raw := FileAccess.get_file_as_string(_input_path)
	var payload: Variant = JSON.parse_string(raw)
	if not payload is Dictionary:
		push_error("portrait input must be a JSON object")
		quit(2)
		return
	var candidate := payload as Dictionary
	var candidate_id := String(candidate.get("candidate_id", ""))
	var species_id := String(candidate.get("species_id", ""))
	var appearance: Variant = candidate.get("appearance", {})
	if candidate_id.is_empty() or (species_id != "fox" and species_id != "dog"):
		push_error("portrait input has invalid identity")
		quit(2)
		return
	if not appearance is Dictionary:
		push_error("portrait input has invalid appearance")
		quit(2)
		return
	var scene := load("res://characters/%s/%s.tscn" % [species_id, species_id]) as PackedScene
	if scene == null:
		push_error("portrait scene is unavailable for %s" % species_id)
		quit(3)
		return
	var full := await _render_view(scene, candidate_id, appearance as Dictionary, FULL_SIZE, false)
	var head := await _render_view(scene, candidate_id, appearance as Dictionary, HEAD_SIZE, true)
	if full == null or head == null:
		push_error("portrait viewport did not produce an image; a real rendering device is required")
		quit(4)
		return
	DirAccess.make_dir_recursive_absolute(_output_dir)
	var full_path := _output_dir.path_join("%s-full.png" % candidate_id)
	var head_path := _output_dir.path_join("%s-head.png" % candidate_id)
	if full.save_png(full_path) != OK or head.save_png(head_path) != OK:
		push_error("portrait image could not be saved")
		quit(4)
		return
	print(JSON.stringify({"candidate_id": candidate_id, "full_body": full_path, "headshot": head_path}))
	quit()


func _render_view(
	scene: PackedScene,
	identity: String,
	appearance: Dictionary,
	size: Vector2i,
	headshot: bool,
) -> Image:
	var viewport := SubViewport.new()
	viewport.size = size
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.transparent_bg = false
	root.add_child(viewport)
	var world := Node3D.new()
	viewport.add_child(world)
	var environment := WorldEnvironment.new()
	var environment_resource := Environment.new()
	environment_resource.background_mode = Environment.BG_COLOR
	environment_resource.background_color = Color("f4eee5")
	environment_resource.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment_resource.ambient_light_color = Color("fff8ed")
	environment_resource.ambient_light_energy = 0.82
	environment.environment = environment_resource
	world.add_child(environment)
	var key_light := DirectionalLight3D.new()
	key_light.rotation_degrees = Vector3(-32.0, -28.0, 0.0)
	key_light.light_energy = 1.25
	world.add_child(key_light)
	var fill_light := DirectionalLight3D.new()
	fill_light.rotation_degrees = Vector3(-18.0, 145.0, 0.0)
	fill_light.light_energy = 0.55
	world.add_child(fill_light)
	var camera := Camera3D.new()
	world.add_child(camera)
	var actor := scene.instantiate() as ElfieActor
	actor.install_shared_animations = false
	world.add_child(actor)
	actor.configure(identity, Vector3.ZERO, appearance)
	actor.set_physics_process(false)
	await process_frame
	await process_frame
	await process_frame
	var bounds := actor.visual_bounds()
	if headshot:
		# Match the in-app lab's bust framing instead of squeezing the full body
		# into the square species avatar.
		var bust_height := maxf(bounds.size.y * 0.62, 0.5)
		var focus := Vector3(
			bounds.get_center().x,
			bounds.end.y - bust_height * 0.5,
			bounds.get_center().z,
		)
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = maxf(bust_height, bounds.size.x) * 1.12
		camera.position = focus + Vector3(0.0, 0.0, 4.0)
		camera.look_at(focus, Vector3.UP)
	else:
		camera.fov = 42.0
		camera.position = Vector3(0.0, 0.92, 4.35)
		camera.look_at(Vector3(0.0, 0.84, 0.0), Vector3.UP)
	camera.current = true
	await process_frame
	var texture := viewport.get_texture()
	if texture == null:
		viewport.queue_free()
		await process_frame
		push_error("portrait viewport texture is unavailable")
		return null
	var image := texture.get_image()
	viewport.queue_free()
	await process_frame
	if image == null:
		push_error("portrait viewport image is unavailable")
		return null
	return image
