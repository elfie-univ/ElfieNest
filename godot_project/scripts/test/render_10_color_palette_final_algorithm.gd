extends SceneTree

## Final phase-1 palette review.
##
## This replays the accepted color algorithm from
## render_appearance_variation_experiments.gd, but renders each real 3D view
## first and then applies only the pixel-wise source-fur tone transfer. It does
## not apply the rejected fixed-camera pattern masks, and it does not modify
## GLB, manifests, or runtime code.
##
## The 13 semantic regions remain a separate 3D validation asset in
## render_appearance_region_debug.gd. They are not mixed into this solid-coat
## plate, because doing so would test local patterns rather than base color.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")

const IMAGE_SIZE := Vector2i(256, 256)
const GRID_COLUMNS := 5
const BACKGROUND := Color("707079")
const OUTPUT_RELATIVE := "res://../docs/public/assets/appearance-experiments/phase-1/10-color-palette-final"

const ANGLES: Array[Dictionary] = [
	{"id": "front", "position": Vector3(0.0, 0.96, 3.85)},
	{"id": "three_quarter", "position": Vector3(2.55, 1.00, 3.05)},
	{"id": "side", "position": Vector3(3.85, 0.98, 0.0)},
]

const DOG_PALETTE: Array[Dictionary] = [
	{"id": "snow_white", "color": Color("efe8dc")},
	{"id": "ivory", "color": Color("e3cda7")},
	{"id": "cream", "color": Color("d8ad76")},
	{"id": "honey_gold", "color": Color("c9884b")},
	{"id": "apricot", "color": Color("d77b4d")},
	{"id": "russet", "color": Color("9d4e32")},
	{"id": "chestnut", "color": Color("814b34")},
	{"id": "chocolate", "color": Color("653b2c")},
	{"id": "silver_gray", "color": Color("7a8288")},
	{"id": "smoky_charcoal", "color": Color("4a4d52")},
]

const FOX_PALETTE: Array[Dictionary] = [
	{"id": "ivory", "color": Color("e2d3bd")},
	{"id": "cream", "color": Color("d7ae7d")},
	{"id": "champagne", "color": Color("d8b778")},
	{"id": "golden", "color": Color("c98542")},
	{"id": "orange_red", "color": Color("c95a2d")},
	{"id": "fox_red", "color": Color("a8442b")},
	{"id": "chestnut", "color": Color("713828")},
	{"id": "sable_brown", "color": Color("664233")},
	{"id": "silver_gray", "color": Color("7a8288")},
	{"id": "smoky_black", "color": Color("45474c")},
]

var _output_dir := ""


func _init() -> void:
	call_deferred("_render")


func _render() -> void:
	var configured_output := OS.get_environment("PALETTE_OUTPUT_DIR")
	var output_source := OUTPUT_RELATIVE if configured_output.is_empty() else configured_output
	_output_dir = (
		ProjectSettings.globalize_path(output_source)
		if output_source.begins_with("res://")
		else output_source
	)
	DirAccess.make_dir_recursive_absolute(_output_dir)
	await _render_species("dog", DOG_SCENE, DOG_PALETTE)
	await _render_species("fox", FOX_SCENE, FOX_PALETTE)
	print("PALETTE_FINAL_ALGORITHM: dog=10 fox=10 views=front,three_quarter,side")
	print("PALETTE_FINAL_RENDER_OUTPUT: %s" % _output_dir)
	quit()


func _render_species(
	species_id: String,
	scene: PackedScene,
	palette: Array[Dictionary],
) -> void:
	var view_grids: Array[Image] = []
	for angle: Dictionary in ANGLES:
		var source := await _render_source(scene, angle["position"] as Vector3)
		var tiles: Array[Image] = []
		for index in range(palette.size()):
			var item: Dictionary = palette[index]
			var render := _tone_image(
				species_id,
				source,
				item["color"] as Color,
			)
			render.save_png(
				"%s/%s-%s-%02d-%s.png"
				% [_output_dir, species_id, String(angle["id"]), index + 1, String(item["id"])]
			)
			tiles.append(render)
		var grid := _join_grid(tiles)
		grid.save_png(
			"%s/%s-10-color-%s.png" % [_output_dir, species_id, String(angle["id"])]
		)
		view_grids.append(grid)
	_join_vertical(view_grids).save_png("%s/%s-10-color-3views.png" % [_output_dir, species_id])


func _render_source(scene: PackedScene, camera_position: Vector3) -> Image:
	var viewport := SubViewport.new()
	viewport.size = IMAGE_SIZE
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.transparent_bg = false
	root.add_child(viewport)

	var world := Node3D.new()
	viewport.add_child(world)
	var environment := WorldEnvironment.new()
	var environment_resource := Environment.new()
	environment_resource.background_mode = Environment.BG_COLOR
	environment_resource.background_color = BACKGROUND
	environment_resource.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment_resource.ambient_light_color = Color.WHITE
	environment_resource.ambient_light_energy = 1.0
	environment.environment = environment_resource
	world.add_child(environment)

	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-28.0, -25.0, 0.0)
	light.light_energy = 1.0
	world.add_child(light)

	var camera := Camera3D.new()
	camera.position = camera_position
	camera.fov = 36.0
	world.add_child(camera)
	camera.look_at(Vector3(0.0, 0.88, 0.0), Vector3.UP)
	camera.current = true

	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)
	await process_frame
	await process_frame
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


func _tone_image(species_id: String, source: Image, target: Color) -> Image:
	var output := source.duplicate()
	var mid_luma := 0.62 if species_id == "dog" else 0.56
	var target_luma := maxf(_luminance(target), 0.001)
	var target_chroma := target / target_luma
	for y in range(IMAGE_SIZE.y):
		for x in range(IMAGE_SIZE.x):
			var source_pixel := source.get_pixel(x, y)
			if not _is_subject_pixel(source_pixel):
				continue
			var source_luma := _luminance(source_pixel)
			var dark_feature := 1.0 - _smoothstep(0.08, 0.28, source_luma)
			var high := maxf(source_pixel.r, maxf(source_pixel.g, source_pixel.b))
			var low := minf(source_pixel.r, minf(source_pixel.g, source_pixel.b))
			var neutrality := low / maxf(high, 0.001)
			var light_region := (
				_smoothstep(0.52, 0.76, source_luma)
				* _smoothstep(0.48, 0.76, neutrality)
			)
			var relative_luma := pow(source_luma / maxf(mid_luma, 0.001), 0.78)
			var output_luma := clampf(target_luma * relative_luma, 0.015, 0.985)
			var recolored := Color(
				clampf(target_chroma.r * output_luma, 0.0, 1.0),
				clampf(target_chroma.g * output_luma, 0.0, 1.0),
				clampf(target_chroma.b * output_luma, 0.0, 1.0),
				source_pixel.a,
			)
			var preserve := maxf(dark_feature, light_region)
			output.set_pixel(x, y, recolored.lerp(source_pixel, clampf(preserve, 0.0, 1.0)))
	return output


func _is_subject_pixel(pixel: Color) -> bool:
	return maxf(
		absf(pixel.r - BACKGROUND.r),
		maxf(absf(pixel.g - BACKGROUND.g), absf(pixel.b - BACKGROUND.b)),
	) > 0.035


func _luminance(color: Color) -> float:
	return color.r * 0.299 + color.g * 0.587 + color.b * 0.114


func _smoothstep(edge0: float, edge1: float, value: float) -> float:
	var t := clampf((value - edge0) / (edge1 - edge0), 0.0, 1.0)
	return t * t * (3.0 - 2.0 * t)


func _join_grid(images: Array[Image]) -> Image:
	var rows := int(ceil(float(images.size()) / float(GRID_COLUMNS)))
	var output := Image.create(
		IMAGE_SIZE.x * GRID_COLUMNS,
		IMAGE_SIZE.y * rows,
		false,
		Image.FORMAT_RGBA8,
	)
	output.fill(Color("f2eee7"))
	for index in range(images.size()):
		var x := (index % GRID_COLUMNS) * IMAGE_SIZE.x
		var y := (index / GRID_COLUMNS) * IMAGE_SIZE.y
		output.blit_rect(images[index], Rect2i(Vector2i.ZERO, IMAGE_SIZE), Vector2i(x, y))
	return output


func _join_vertical(images: Array[Image]) -> Image:
	var width := 0
	var height := 0
	for image in images:
		width = maxi(width, image.get_width())
		height += image.get_height()
	var output := Image.create(width, height, false, Image.FORMAT_RGBA8)
	output.fill(Color("f2eee7"))
	var y_offset := 0
	for image in images:
		output.blit_rect(image, Rect2i(Vector2i.ZERO, image.get_size()), Vector2i(0, y_offset))
		y_offset += image.get_height()
	return output
