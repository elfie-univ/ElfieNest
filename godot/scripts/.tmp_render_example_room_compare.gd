extends SceneTree

const FRAME_SIZE := Vector2i(1024, 768)
const OUTPUT_DIR := "/tmp/elfienest-example-room"


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var directory_error := DirAccess.make_dir_recursive_absolute(OUTPUT_DIR)
	if directory_error != OK:
		push_error("Cannot create output directory: %s" % OUTPUT_DIR)
		quit(1)
		return

	root.size = FRAME_SIZE
	var packed_scene := load("res://example_room.tscn") as PackedScene
	if packed_scene == null:
		push_error("Cannot load res://example_room.tscn")
		quit(1)
		return

	var room := packed_scene.instantiate() as Node3D
	root.add_child(room)
	_add_environment(room)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.near = 0.05
	camera.far = 250.0
	camera.current = true
	room.add_child(camera)

	await _wait_frames(12)
	var specs := [
		{
			"filename": "00_overview.png",
			"target": Vector3(0.0, 0.65, -19.0),
			"offset": Vector3(22.0, 28.0, 26.0),
			"size": 52.0,
		},
		{
			"filename": "01_portal_and_first_rooms.png",
			"target": Vector3(0.0, 0.8, -2.0),
			"offset": Vector3(13.0, 15.0, 14.0),
			"size": 17.0,
		},
		{
			"filename": "02_middle_rooms.png",
			"target": Vector3(0.0, 0.8, -19.0),
			"offset": Vector3(13.0, 15.0, 14.0),
			"size": 17.0,
		},
		{
			"filename": "03_last_rooms.png",
			"target": Vector3(0.0, 0.8, -36.0),
			"offset": Vector3(13.0, 15.0, 14.0),
			"size": 17.0,
		},
	]

	for spec in specs:
		camera.size = float(spec["size"])
		camera.position = spec["target"] + spec["offset"]
		camera.look_at(spec["target"], Vector3.UP)
		await _wait_frames(4)
		await RenderingServer.frame_post_draw
		var image := root.get_texture().get_image()
		var output_path := OUTPUT_DIR.path_join(String(spec["filename"]))
		var save_error := image.save_png(output_path)
		if save_error != OK:
			push_error("Cannot save screenshot: %s" % output_path)
			quit(1)
			return
		print("CAPTURED: %s" % output_path)

	room.queue_free()
	quit(0)


func _add_environment(parent: Node3D) -> void:
	var world_environment := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.72, 0.78, 0.81)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.94, 0.94, 0.94)
	environment.ambient_light_energy = 0.3
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	world_environment.environment = environment
	parent.add_child(world_environment)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-58.0, -32.0, 0.0)
	sun.light_energy = 0.45
	sun.shadow_enabled = true
	parent.add_child(sun)

	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-48.0, 142.0, 0.0)
	fill.light_energy = 0.08
	fill.shadow_enabled = false
	parent.add_child(fill)


func _wait_frames(frame_count: int) -> void:
	for _frame in range(frame_count):
		await process_frame
