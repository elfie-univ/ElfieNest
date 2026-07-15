extends SceneTree

const NEST_SCENE := preload("res://rooms/nest.tscn")
const D := preload("res://rooms/room_dimensions.gd")
const FRAME_SIZE := Vector2i(1024, 768)
const CONTACT_COLUMNS: int = 4
const THUMBNAIL_SIZE := Vector2i(512, 384)

var _output_dir := "/tmp/elfienest-room-closeups"


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--output-dir="):
			_output_dir = argument.trim_prefix("--output-dir=")
	var directory_error := DirAccess.make_dir_recursive_absolute(_output_dir)
	if directory_error != OK:
		push_error("Cannot create close-up output directory: %s" % _output_dir)
		quit(1)
		return

	root.size = FRAME_SIZE
	var nest := NEST_SCENE.instantiate() as Node3D
	root.add_child(nest)
	await _wait_frames(5)
	var camera := nest.get_node("Camera3D") as Camera3D
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.near = 0.05
	camera.far = 200.0
	camera.current = true

	var specs: Array[Dictionary] = []
	var building_center_z := -4.0 * D.CELL_PITCH
	specs.append(_spec("00_overview.png", Vector3(0.2, 0.6, building_center_z), Vector3(22.0, 28.0, 26.0), 52.0))
	var room_names := ["kitchen", "sitting", "media", "gym", "garden", "working", "music", "bookroom"]
	for index in range(8):
		specs.append(_spec(
			"%02d_activity_%s.png" % [index + 1, room_names[index]],
			Vector3(D.ACTIVITY_CENTER_X, 0.9, D.cell_center_z(index)),
			Vector3(7.0, 5.2, 4.5),
			6.8
		))
	for index in [0, 7]:
		specs.append(_spec(
			"%02d_dorm.png" % (index + 1),
			Vector3(D.DORM_CENTER_X, 0.65, D.cell_center_z(index)),
			Vector3(-4.5, 7.5, 1.6),
			6.4
		))
	specs.append(_spec(
		"11_corridor.png",
		Vector3(0.0, 0.45, building_center_z),
		Vector3(8.0, 9.0, 14.0),
		25.0
	))

	var captures: Array[Image] = []
	for spec in specs:
		var image := await _capture(
			camera,
			spec["target"] as Vector3,
			spec["offset"] as Vector3,
			float(spec["size"])
		)
		var output_path := _output_dir.path_join(String(spec["filename"]))
		var save_error := image.save_png(output_path)
		if save_error != OK:
			push_error("Cannot save close-up: %s" % output_path)
			quit(1)
			return
		captures.append(image)
		print("CAPTURED: %s" % output_path)

	var contact_error := _save_contact_sheet(captures, _output_dir.path_join("contact_sheet.png"))
	if contact_error != OK:
		push_error("Cannot save contact sheet")
		quit(1)
		return
	print("PASS: rendered %d room views and contact sheet" % captures.size())
	nest.queue_free()
	quit(0)


func _spec(filename: String, target: Vector3, offset: Vector3, size: float) -> Dictionary:
	return {
		"filename": filename,
		"target": target,
		"offset": offset,
		"size": size,
	}


func _capture(camera: Camera3D, target: Vector3, offset: Vector3, size: float) -> Image:
	camera.size = size
	camera.position = target + offset
	camera.look_at(target, Vector3.UP)
	await _wait_frames(3)
	await RenderingServer.frame_post_draw
	return root.get_texture().get_image()


func _save_contact_sheet(images: Array[Image], output_path: String) -> Error:
	var rows := ceili(float(images.size()) / float(CONTACT_COLUMNS))
	var sheet := Image.create_empty(
		THUMBNAIL_SIZE.x * CONTACT_COLUMNS,
		THUMBNAIL_SIZE.y * rows,
		false,
		Image.FORMAT_RGBA8
	)
	sheet.fill(Color("#202429"))
	for index in range(images.size()):
		var thumbnail := images[index].duplicate()
		thumbnail.convert(Image.FORMAT_RGBA8)
		thumbnail.resize(THUMBNAIL_SIZE.x, THUMBNAIL_SIZE.y, Image.INTERPOLATE_LANCZOS)
		var destination := Vector2i(
			(index % CONTACT_COLUMNS) * THUMBNAIL_SIZE.x,
			(index / CONTACT_COLUMNS) * THUMBNAIL_SIZE.y
		)
		sheet.blit_rect(thumbnail, Rect2i(Vector2i.ZERO, THUMBNAIL_SIZE), destination)
	return sheet.save_png(output_path)


func _wait_frames(frame_count: int) -> void:
	for frame in range(frame_count):
		await process_frame
