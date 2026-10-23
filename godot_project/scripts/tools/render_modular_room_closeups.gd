extends SceneTree

const NEST_SCENE := preload("res://rooms/nest.tscn")
const FRAME_SIZE := Vector2i(1024, 768)
const CONTACT_COLUMNS: int = 4
const THUMBNAIL_SIZE := Vector2i(512, 384)

var _output_dir := ProjectSettings.globalize_path("res://../build/estate-closeups")


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
	var nest := NEST_SCENE.instantiate() as ModularNest
	nest.show_observation_hud = false
	root.add_child(nest)
	await _wait_frames(5)
	var captures: Array[Image] = []
	var views := nest.observer_camera_catalog()["views"] as Array
	for view: Dictionary in views:
		var view_id := String(view["id"])
		if not nest.select_observer_camera_by_id(view_id):
			push_error("Cannot select complete estate view: %s" % view_id)
			quit(1)
			return
		await _wait_frames(3)
		await RenderingServer.frame_post_draw
		var image := root.get_texture().get_image()
		var output_path := _output_dir.path_join("%s.png" % view_id)
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
	print("PASS: rendered %d complete estate views and contact sheet" % captures.size())
	nest.queue_free()
	quit(0)


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
