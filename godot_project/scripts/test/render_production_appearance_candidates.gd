extends SceneTree

## Production appearance acceptance render.
##
## This is an evidence harness, not a second appearance implementation. Every
## tile below goes through ActorAppearance.apply(), the same path used by an
## actor preview. The five recipes mirror the first five V9 batch slots and
## are intentionally explicit so the output can be replayed and audited.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")

const IMAGE_SIZE := Vector2i(384, 384)
const BACKGROUND := Color("707079")
const DEFAULT_OUTPUT_DIR := "/private/tmp/elfienest-appearance-reference/final-v9"

const ANGLES: Array[Dictionary] = [
	{"id": "front", "position": Vector3(0.0, 0.96, 3.85)},
	{"id": "three_quarter", "position": Vector3(2.55, 1.00, 3.05)},
	{"id": "side", "position": Vector3(3.85, 0.98, 0.0)},
]

const DOG_VARIANTS: Array[Dictionary] = [
	{
		"id": "dog-01-ivory-base",
		"primary": "ivory",
		"recipe": "base",
		"marking": "none",
		"placement": "none",
		"marking_color": "ivory",
		"accents": [],
	},
	{
		"id": "dog-02-honey-tuft-crescent",
		"primary": "honey_gold",
		"recipe": "head_tuft_honey",
		"marking": "crescent",
		"placement": "forehead_center",
		"marking_color": "ivory",
		"accents": [
			{"region_id": "head_tuft", "color_id": "honey_gold", "grade_id": "L1", "intensity": 0.82},
		],
	},
	{
		"id": "dog-03-apricot-ear-tip",
		"primary": "apricot",
		"recipe": "ear_tip_silver",
		"marking": "none",
		"placement": "none",
		"marking_color": "ivory",
		"accents": [
			{"region_id": "ear_tip_pair", "color_id": "silver_gray", "grade_id": "D1", "intensity": 0.78},
		],
	},
	{
		"id": "dog-04-russet-forearm-blush",
		"primary": "russet",
		"recipe": "forearm_chocolate",
		"marking": "blush",
		"placement": "cheek_pair",
		"marking_color": "cream",
		"accents": [
			{"region_id": "forearm_paw_pair", "color_id": "chocolate", "grade_id": "D1", "intensity": 0.76},
		],
	},
	{
		"id": "dog-05-silver-chest",
		"primary": "silver_gray",
		"recipe": "chest_apricot",
		"marking": "none",
		"placement": "none",
		"marking_color": "ivory",
		"accents": [
			{"region_id": "chest_tuft", "color_id": "apricot", "grade_id": "L1", "intensity": 0.72},
		],
	},
]

const FOX_VARIANTS: Array[Dictionary] = [
	{
		"id": "fox-01-ivory-base",
		"primary": "ivory",
		"recipe": "base",
		"marking": "none",
		"placement": "none",
		"marking_color": "ivory",
		"accents": [],
	},
	{
		"id": "fox-02-golden-tuft-crescent",
		"primary": "golden",
		"recipe": "head_tuft_golden",
		"marking": "crescent",
		"placement": "forehead_center",
		"marking_color": "ivory",
		"accents": [
			{"region_id": "head_tuft", "color_id": "golden", "grade_id": "L1", "intensity": 0.82},
		],
	},
	{
		"id": "fox-03-orange-ear-tip",
		"primary": "orange_red",
		"recipe": "ear_tip_silver",
		"marking": "none",
		"placement": "none",
		"marking_color": "ivory",
		"accents": [
			{"region_id": "ear_tip_pair", "color_id": "silver_gray", "grade_id": "D1", "intensity": 0.78},
		],
	},
	{
		"id": "fox-04-red-forearm-blush",
		"primary": "fox_red",
		"recipe": "forearm_sable",
		"marking": "blush",
		"placement": "cheek_pair",
		"marking_color": "cream",
		"accents": [
			{"region_id": "forearm_paw_pair", "color_id": "sable_brown", "grade_id": "D1", "intensity": 0.76},
		],
	},
	{
		"id": "fox-05-silver-chest",
		"primary": "silver_gray",
		"recipe": "chest_champagne",
		"marking": "none",
		"placement": "none",
		"marking_color": "ivory",
		"accents": [
			{"region_id": "chest_tuft", "color_id": "champagne", "grade_id": "L1", "intensity": 0.72},
		],
	},
]

var _output_dir := DEFAULT_OUTPUT_DIR


func _init() -> void:
	var configured_output := OS.get_environment("APPEARANCE_CANDIDATE_OUTPUT")
	if not configured_output.is_empty():
		_output_dir = configured_output
	call_deferred("_render")


func _render() -> void:
	DirAccess.make_dir_recursive_absolute(_output_dir)
	var dog_plate := await _render_species("dog", DOG_SCENE, DOG_VARIANTS)
	var fox_plate := await _render_species("fox", FOX_SCENE, FOX_VARIANTS)
	dog_plate.save_png("%s/dog-v9-five-candidates-3views.png" % _output_dir)
	fox_plate.save_png("%s/fox-v9-five-candidates-3views.png" % _output_dir)
	_join_vertical([dog_plate, fox_plate]).save_png(
		"%s/dog-fox-v9-five-candidates-3views.png" % _output_dir
	)
	_write_catalog()
	print("APPEARANCE_V9_CANDIDATES_OUTPUT: %s" % _output_dir)
	print("APPEARANCE_V9_CANDIDATES: dog=5 fox=5 views=front,three_quarter,side")
	quit()


func _render_species(
	species_id: String,
	scene: PackedScene,
	variants: Array[Dictionary],
) -> Image:
	var rows: Array[Image] = []
	for angle: Dictionary in ANGLES:
		var cells: Array[Image] = []
		for variant: Dictionary in variants:
			var image := await _render_candidate(species_id, scene, angle, variant)
			image.save_png(
				"%s/%s-%s.png" % [_output_dir, String(variant["id"]), String(angle["id"])]
			)
			cells.append(image)
		rows.append(_join_horizontal(cells))
	return _join_vertical(rows)


func _render_candidate(
	species_id: String,
	scene: PackedScene,
	angle: Dictionary,
	variant: Dictionary,
) -> Image:
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
	camera.position = angle["position"]
	camera.fov = 36.0
	world.add_child(camera)
	camera.look_at(Vector3(0.0, 0.88, 0.0), Vector3.UP)
	camera.current = true

	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)
	var visual_root := actor.get_node_or_null("VisualRoot") as Node3D
	var collision_shape := actor.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if visual_root == null or collision_shape == null:
		push_error("Actor scene is missing appearance nodes: %s" % species_id)
		viewport.queue_free()
		await process_frame
		return Image.create(IMAGE_SIZE.x, IMAGE_SIZE.y, false, Image.FORMAT_RGBA8)
	ACTOR_APPEARANCE.apply(
		visual_root,
		collision_shape,
		{"material_parameters": _appearance_parameters(species_id, variant)},
		species_id,
	)

	await process_frame
	await process_frame
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


func _appearance_parameters(species_id: String, variant: Dictionary) -> Dictionary:
	var is_dog := species_id == "dog"
	var ivory := "snow_white" if is_dog else "ivory"
	var primary := String(variant["primary"])
	var accents: Array = variant["accents"]
	var parameters: Dictionary = {
		"palette_id": primary,
		"pattern_id": "solid" if is_dog else "classic",
		"pattern_layout_id": "solid" if is_dog else "classic",
		"primary_color_id": primary,
		"secondary_color_id": ivory,
		"accent_color_id": ivory,
		"face_mask_color_id": ivory,
		"marking_color_id": String(variant["marking_color"]),
		"marking_id": String(variant["marking"]),
		"marking_placement": String(variant["placement"]),
		"marking_scale": 0.9,
		"marking_intensity": 0.95 if String(variant["marking"]) != "none" else 0.0,
	}
	for slot in range(3):
		parameters["region_%d_id" % slot] = "none"
		parameters["region_%d_intensity" % slot] = 0.0
		parameters["region_%d_grade_id" % slot] = "L1"
		parameters["region_%d_source_mid_luma" % slot] = 0.62 if is_dog else 0.56
	for slot in range(mini(accents.size(), 3)):
		var accent: Dictionary = accents[slot]
		parameters["region_%d_id" % slot] = String(accent["region_id"])
		parameters["region_%d_color_id" % slot] = String(accent["color_id"])
		parameters["region_%d_grade_id" % slot] = String(accent["grade_id"])
		parameters["region_%d_intensity" % slot] = float(accent["intensity"])
	return parameters


func _write_catalog() -> void:
	var payload := {
		"schema": "appearance-v9-production-candidates.v1",
		"source": "ActorAppearance.apply",
		"views": ["front", "three_quarter", "side"],
		"candidate_count": 5,
		"species": {
			"dog": DOG_VARIANTS,
			"fox": FOX_VARIANTS,
		},
		"constraints": {
			"max_region_accents": 2,
			"max_marks": 1,
			"max_forehead_marks": 1,
			"glb_changed": false,
			"blend_shapes_changed": false,
		},
	}
	var catalog := FileAccess.open("%s/v9-candidate-catalog.json" % _output_dir, FileAccess.WRITE)
	if catalog == null:
		push_error("Unable to write V9 candidate catalog")
		return
	catalog.store_string(JSON.stringify(payload, "\t"))
	catalog.close()


func _join_horizontal(images: Array[Image]) -> Image:
	var output := Image.create(IMAGE_SIZE.x * images.size(), IMAGE_SIZE.y, false, Image.FORMAT_RGBA8)
	for index in range(images.size()):
		output.blit_rect(
			images[index],
			Rect2i(Vector2i.ZERO, IMAGE_SIZE),
			Vector2i(index * IMAGE_SIZE.x, 0),
		)
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
		output.blit_rect(
			image,
			Rect2i(Vector2i.ZERO, image.get_size()),
			Vector2i(0, y_offset),
		)
		y_offset += image.get_height()
	return output
