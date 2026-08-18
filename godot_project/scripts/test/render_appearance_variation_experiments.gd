extends SceneTree

## Phase 2 visual experiments.
##
## Godot renders the original 3D scene first. The accepted phase-1 relative
## tone transfer is then applied to that rendered image, with explicit 2D
## natural-region masks for this fixed adoption-card camera. This is a visual
## feasibility harness only; it does not modify GLB, scenes, or production
## appearance materials, and it does not claim multi-angle 3D stability.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")
const IMAGE_SIZE := Vector2i(512, 512)
const OUTPUT_DIR := "/private/tmp/elfienest-appearance-reference/phase-2"
const BACKGROUND := Color("707079")

const DOG := 0
const FOX := 1

const DOG_COLORS := {
	"golden": Color("d9995b"),
	"silver": Color("7b7e84"),
	"cream": Color("d7b27e"),
	"chocolate": Color("5d392a"),
}
const FOX_COLORS := {
	"red": Color("d9693e"),
	"silver": Color("7b7e84"),
	"cream": Color("d7b27e"),
	"sable": Color("67402f"),
}
const IVORY := Color("e6ddd0")
const DARK_ACCENT := Color("3d2b26")

var _source_images: Dictionary = {}
var _tone_cache: Dictionary = {}


func _init() -> void:
	call_deferred("_render")


func _render() -> void:
	DirAccess.make_dir_recursive_absolute(OUTPUT_DIR)
	_source_images[DOG] = await _render_source(DOG)
	_source_images[FOX] = await _render_source(FOX)

	var requested_stage := OS.get_environment("APPEARANCE_EXPERIMENT_STAGE")
	if not requested_stage.is_empty():
		_render_requested_stage(requested_stage)
		quit()
		return

	var baseline := _render_baseline()
	var patterns := _render_patterns()
	var slots := _render_slots()
	var markings := _render_markings()
	var safe_zones := _render_safe_zones()
	var diversity := _render_diversity()
	_join_vertical([baseline, patterns, slots, markings, safe_zones, diversity]).save_png(
		"%s/phase-2-all-stages.png" % OUTPUT_DIR
	)
	print("APPEARANCE_PHASE_2: baseline,patterns,slots,markings,safe_zones,diversity")
	print("SAFE_ZONE_REJECTED: dog=1 fox=1")
	print("FIVE_CANDIDATE_KEYS: dog=5 fox=5")
	quit()


func _render_requested_stage(stage: String) -> void:
	match stage:
		"baseline":
			_render_baseline()
		"patterns":
			_render_patterns()
		"slots":
			_render_slots()
		"markings":
			_render_markings()
		"safe_zones":
			_render_safe_zones()
		"diversity":
			_render_diversity()
		_:
			push_error("Unknown APPEARANCE_EXPERIMENT_STAGE: %s" % stage)


func _render_baseline() -> Image:
	var result := _join_vertical([_render_color_row(DOG), _render_color_row(FOX)])
	result.save_png("%s/01-accepted-baseline.png" % OUTPUT_DIR)
	return result


func _render_patterns() -> Image:
	var result := _join_vertical([_render_pattern_row(DOG), _render_pattern_row(FOX)])
	result.save_png("%s/02-large-natural-patterns.png" % OUTPUT_DIR)
	return result


func _render_slots() -> Image:
	var result := _join_vertical([_render_slot_row(DOG), _render_slot_row(FOX)])
	result.save_png("%s/03-color-slot-permutations.png" % OUTPUT_DIR)
	return result


func _render_markings() -> Image:
	var result := _join_vertical([_render_marking_row(DOG), _render_marking_row(FOX)])
	result.save_png("%s/04-local-markings.png" % OUTPUT_DIR)
	return result


func _render_safe_zones() -> Image:
	var result := _join_vertical([_render_safe_zone_row(DOG), _render_safe_zone_row(FOX)])
	result.save_png("%s/05-safe-zone-validation.png" % OUTPUT_DIR)
	return result


func _render_diversity() -> Image:
	var result := _join_vertical([_render_diversity_row(DOG), _render_diversity_row(FOX)])
	result.save_png("%s/06-five-candidate-diversity.png" % OUTPUT_DIR)
	return result


func _render_color_row(species: int) -> Image:
	var names: Array = (
		["original", "silver", "cream", "chocolate"]
		if species == DOG
		else ["original", "silver", "cream", "sable"]
	)
	var images: Array[Image] = []
	for name: String in names:
		if name == "original":
			images.append(_source_images[species] as Image)
		else:
			var color := _palette(species, name)
			images.append(_variant(species, color, IVORY, 0, 0, 0, true))
	return _join_horizontal(images)


func _render_pattern_row(species: int) -> Image:
	var images: Array[Image] = []
	var primary := _palette(species, "chocolate" if species == DOG else "sable")
	# Dog uses chest, blaze and paw-sock regions here; the tuft is kept for
	# later local-mark experiments because a coarse front mask reads as a sticker.
	var layouts: Array = [0, 1, 2, 4] if species == DOG else [0, 1, 5, 6]
	var secondary := _palette(species, "cream") if species == DOG else IVORY
	for layout: int in layouts:
		var preserve_light := layout == 0
		images.append(_variant(species, primary, secondary, layout, 0, 0, preserve_light))
	return _join_horizontal(images)


func _render_slot_row(species: int) -> Image:
	var warm := _palette(species, "chocolate" if species == DOG else "sable")
	var cool := _palette(species, "silver")
	var images: Array[Image] = [
		_variant(species, warm, IVORY, 1, 0, 0, false),
		_variant(species, IVORY, warm, 1, 0, 0, false),
		_variant(species, cool, IVORY, 1, 0, 0, false),
		_variant(species, IVORY, cool, 1, 0, 0, false),
	]
	return _join_horizontal(images)


func _render_marking_row(species: int) -> Image:
	var primary := _palette(species, "golden" if species == DOG else "red")
	var images: Array[Image] = []
	var placements: Array[int] = [1, 1, 1, 2, 2, 3]
	for index in range(6):
		images.append(_variant(species, primary, IVORY, 0, index + 1, placements[index], false))
	return _join_horizontal(images)


func _render_safe_zone_row(species: int) -> Image:
	# Keep the marks legible in the validation plate; the rule itself is color-agnostic.
	var primary := _palette(species, "cream")
	var images: Array[Image] = [
		_variant(species, primary, IVORY, 0, 1, 1, false),
		_variant(species, primary, IVORY, 0, 2, 2, false),
		_variant(species, primary, IVORY, 0, 3, 3, false),
		# Placement 4 is an eye/nose request and is rejected by _safe_zone().
		_variant(species, primary, IVORY, 0, 1, 4, false),
	]
	return _join_horizontal(images)


func _render_diversity_row(species: int) -> Image:
	var specs: Array[Dictionary] = [
		{"primary": "golden", "secondary": "cream", "layout": 0, "mark": 0, "placement": 0},
		{"primary": "silver", "secondary": "cream", "layout": 1, "mark": 1, "placement": 1},
		{"primary": "chocolate", "secondary": "ivory", "layout": 2, "mark": 3, "placement": 2},
		{"primary": "cream", "secondary": "silver", "layout": 4, "mark": 4, "placement": 3},
		{"primary": "silver", "secondary": "ivory", "layout": 4, "mark": 6, "placement": 1},
	]
	var images: Array[Image] = []
	for item: Dictionary in specs:
		var primary_name := String(item["primary"])
		var secondary_name := String(item["secondary"])
		if species == FOX:
			primary_name = _fox_color_alias(primary_name)
			secondary_name = _fox_color_alias(secondary_name)
		var key := "%s|%s|%d|%d|%d" % [
			primary_name,
			secondary_name,
			int(item["layout"]),
			int(item["mark"]),
			int(item["placement"]),
		]
		print("candidate[%s]: %s" % ["dog" if species == DOG else "fox", key])
		images.append(
			_variant(
				species,
				_palette(species, primary_name),
				_palette(species, secondary_name),
				int(item["layout"]),
				int(item["mark"]),
				int(item["placement"]),
				false,
			)
		)
	return _join_horizontal(images)


func _render_source(species: int) -> Image:
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
	camera.position = Vector3(0.0, 0.96, 3.85)
	camera.fov = 36.0
	world.add_child(camera)
	camera.look_at(Vector3(0.0, 0.88, 0.0), Vector3.UP)
	camera.current = true

	var scene: PackedScene = DOG_SCENE if species == DOG else FOX_SCENE
	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)

	await process_frame
	await process_frame
	await process_frame
	await process_frame
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


func _variant(
	species: int,
	primary: Color,
	secondary: Color,
	layout: int,
	marking: int,
	placement: int,
	preserve_light: bool,
) -> Image:
	var source := _source_images[species] as Image
	var primary_image := _tone_image(species, primary, preserve_light)
	var secondary_image := _tone_image(species, secondary, preserve_light and layout == 0)
	var output := source.duplicate()
	for y in range(IMAGE_SIZE.y):
		for x in range(IMAGE_SIZE.x):
			var source_pixel := source.get_pixel(x, y)
			if not _is_subject_pixel(source_pixel):
				continue
			var region := _pattern_alpha(species, layout, x, y)
			var color := primary_image.get_pixel(x, y).lerp(secondary_image.get_pixel(x, y), region)
			var mark := _mark_alpha(species, marking, placement, x, y)
			if mark > 0.0:
				color = color.lerp(DARK_ACCENT, mark)
			output.set_pixel(x, y, color)
	return output


func _tone_image(species: int, target: Color, preserve_light: bool) -> Image:
	var key := "%d:%s:%s" % [species, target.to_html(false), str(preserve_light)]
	if _tone_cache.has(key):
		return _tone_cache[key] as Image
	var source := _source_images[species] as Image
	var output := source.duplicate()
	var mid_luma := 0.62 if species == DOG else 0.56
	for y in range(IMAGE_SIZE.y):
		for x in range(IMAGE_SIZE.x):
			var source_pixel := source.get_pixel(x, y)
			if not _is_subject_pixel(source_pixel):
				continue
			var source_luma := _luminance(source_pixel)
			var dark_feature := 1.0 - _smoothstep(0.08, 0.28, source_luma)
			var max_channel := maxf(source_pixel.r, maxf(source_pixel.g, source_pixel.b))
			var min_channel := minf(source_pixel.r, minf(source_pixel.g, source_pixel.b))
			var neutrality := min_channel / maxf(max_channel, 0.001)
			var light_region := _smoothstep(0.52, 0.76, source_luma) * _smoothstep(0.48, 0.76, neutrality)
			var relative_luma := pow(source_luma / maxf(mid_luma, 0.001), 0.78)
			var target_luma := maxf(_luminance(target), 0.001)
			var output_luma := clampf(target_luma * relative_luma, 0.015, 0.985)
			var target_chroma := target / target_luma
			var color := Color(
				clampf(target_chroma.r * output_luma, 0.0, 1.0),
				clampf(target_chroma.g * output_luma, 0.0, 1.0),
				clampf(target_chroma.b * output_luma, 0.0, 1.0),
				source_pixel.a,
			)
			var preserve := dark_feature
			if preserve_light:
				preserve = maxf(preserve, light_region)
			output.set_pixel(x, y, color.lerp(source_pixel, clampf(preserve, 0.0, 1.0)))
	_tone_cache[key] = output
	return output


func _pattern_alpha(species: int, layout: int, x: int, y: int) -> float:
	if layout == 0:
		return 0.0
	if species == DOG:
		if layout == 1:
			return _ellipse_alpha(x, y, 256.0, 300.0, 68.0, 118.0)
		if layout == 2:
			return _blaze_alpha(x, y)
		if layout == 3:
			return _top_tuft_alpha(x, y)
		if layout == 4:
			return maxf(_ellipse_alpha(x, y, 207.0, 414.0, 34.0, 36.0), _ellipse_alpha(x, y, 306.0, 414.0, 34.0, 36.0))
		return 0.0
	if layout == 1:
		return _ellipse_alpha(x, y, 256.0, 306.0, 62.0, 130.0)
	if layout == 5:
		return maxf(
			_ellipse_alpha(x, y, 206.0, 188.0, 65.0, 48.0),
			maxf(_ellipse_alpha(x, y, 306.0, 188.0, 65.0, 48.0), _ellipse_alpha(x, y, 256.0, 174.0, 78.0, 28.0)),
		)
	if layout == 6:
		return maxf(_ellipse_alpha(x, y, 184.0, 106.0, 28.0, 48.0), _ellipse_alpha(x, y, 328.0, 106.0, 28.0, 48.0))
	return 0.0


func _blaze_alpha(x: int, y: int) -> float:
	if y < 48 or y > 105:
		return 0.0
	var progress := float(y - 48) / 57.0
	var center := 256.0 + sin(progress * PI * 1.25) * 3.5
	var width := 7.0 + sin(progress * PI) * 4.0
	var distance := absf(float(x) - center)
	return 1.0 - _smoothstep(width, width + 3.0, distance)


func _top_tuft_alpha(x: int, y: int) -> float:
	return maxf(
		_ellipse_alpha(x, y, 246.0, 52.0, 13.0, 12.0),
		maxf(_ellipse_alpha(x, y, 259.0, 44.0, 14.0, 14.0), _ellipse_alpha(x, y, 272.0, 53.0, 11.0, 11.0)),
	)


func _mark_alpha(species: int, marking: int, placement: int, x: int, y: int) -> float:
	if marking <= 0 or _safe_zone(species, placement, x, y) <= 0.0:
		return 0.0
	var center := Vector2(256.0, 100.0)
	if placement == 2:
		center = Vector2(207.0 if species == DOG else 214.0, 185.0)
	elif placement == 3:
		center = Vector2(256.0, 292.0 if species == DOG else 306.0)
	var point := (Vector2(x, y) - center) / 24.0
	return _marking_shape(point, marking)


func _safe_zone(species: int, placement: int, x: int, y: int) -> float:
	if placement == 1:
		return _ellipse_alpha(x, y, 256.0, 100.0, 34.0, 34.0)
	if placement == 2:
		return _ellipse_alpha(x, y, 214.0 if species == FOX else 207.0, 185.0, 42.0, 32.0)
	if placement == 3:
		return _ellipse_alpha(x, y, 256.0, 300.0 if species == DOG else 306.0, 72.0, 66.0)
	# Placement 4 represents an invalid eye/nose request; reject at generation.
	return 0.0


func _marking_shape(point: Vector2, marking: int) -> float:
	if marking == 1:
		var outer := 1.0 - _smoothstep(0.44, 0.54, point.length())
		var cutout := 1.0 - _smoothstep(0.38, 0.48, (point - Vector2(0.18, 0.01)).length())
		return outer * (1.0 - cutout)
	if marking == 2:
		return maxf(_segment_alpha(point, Vector2(-0.34, 0.28), Vector2(0.28, 0.28), 0.065), maxf(_segment_alpha(point, Vector2(0.28, 0.28), Vector2(-0.28, -0.02), 0.065), _segment_alpha(point, Vector2(-0.28, -0.02), Vector2(0.34, -0.28), 0.065)))
	if marking == 3:
		return maxf(1.0 - _smoothstep(0.12, 0.18, point.length()), maxf(_segment_alpha(point, Vector2(-0.42, 0.0), Vector2(0.42, 0.0), 0.045), _segment_alpha(point, Vector2(0.0, -0.42), Vector2(0.0, 0.42), 0.045)))
	if marking == 4:
		return maxf(_dot_alpha(point, Vector2(-0.28, 0.18), 0.075), maxf(_dot_alpha(point, Vector2(0.02, 0.30), 0.055), maxf(_dot_alpha(point, Vector2(0.26, 0.08), 0.07), _dot_alpha(point, Vector2(-0.04, -0.20), 0.05))))
	if marking == 5:
		return maxf(_dot_alpha(point, Vector2(-0.22, 0.10), 0.11), _segment_alpha(point, Vector2(-0.10, 0.03), Vector2(0.38, -0.22), 0.055))
	if marking == 6:
		return maxf(_segment_alpha(point, Vector2(0.0, -0.36), Vector2(0.0, 0.36), 0.055), maxf(_segment_alpha(point, Vector2(-0.24, 0.22), Vector2(0.24, 0.22), 0.05), _segment_alpha(point, Vector2(-0.20, -0.20), Vector2(0.22, -0.20), 0.05)))
	return 0.0


func _segment_alpha(point: Vector2, start: Vector2, finish: Vector2, width: float) -> float:
	var along := finish - start
	var projection := clampf((point - start).dot(along) / maxf(along.length_squared(), 0.0001), 0.0, 1.0)
	return 1.0 - _smoothstep(width, width + 0.035, point.distance_to(start.lerp(finish, projection)))


func _dot_alpha(point: Vector2, center: Vector2, radius: float) -> float:
	return 1.0 - _smoothstep(radius, radius + 0.035, point.distance_to(center))


func _ellipse_alpha(x: int, y: int, center_x: float, center_y: float, radius_x: float, radius_y: float) -> float:
	var dx := (float(x) - center_x) / radius_x
	var dy := (float(y) - center_y) / radius_y
	return 1.0 - _smoothstep(0.82, 1.0, sqrt(dx * dx + dy * dy))


func _is_subject_pixel(pixel: Color) -> bool:
	return maxf(absf(pixel.r - BACKGROUND.r), maxf(absf(pixel.g - BACKGROUND.g), absf(pixel.b - BACKGROUND.b))) > 0.035


func _palette(species: int, name: String) -> Color:
	if species == DOG:
		return DOG_COLORS.get(name, IVORY)
	return FOX_COLORS.get(name, IVORY)


func _fox_color_alias(name: String) -> String:
	if name == "golden":
		return "red"
	if name == "chocolate":
		return "sable"
	return name


func _luminance(color: Color) -> float:
	return color.r * 0.299 + color.g * 0.587 + color.b * 0.114


func _smoothstep(edge0: float, edge1: float, value: float) -> float:
	var t := clampf((value - edge0) / (edge1 - edge0), 0.0, 1.0)
	return t * t * (3.0 - 2.0 * t)


func _join_horizontal(images: Array[Image]) -> Image:
	var output := Image.create(IMAGE_SIZE.x * images.size(), IMAGE_SIZE.y, false, Image.FORMAT_RGBA8)
	for index in range(images.size()):
		output.blit_rect(images[index], Rect2i(Vector2i.ZERO, IMAGE_SIZE), Vector2i(index * IMAGE_SIZE.x, 0))
	return output


func _join_vertical(images: Array[Image]) -> Image:
	var width := 0
	var height := 0
	for image in images:
		width = maxi(width, image.get_width())
		height += image.get_height()
	var output := Image.create(width, height, false, Image.FORMAT_RGBA8)
	var y_offset := 0
	for image in images:
		output.blit_rect(image, Rect2i(Vector2i.ZERO, image.get_size()), Vector2i(0, y_offset))
		y_offset += image.get_height()
	return output
