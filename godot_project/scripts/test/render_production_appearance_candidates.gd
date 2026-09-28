extends SceneTree

## Formal 3D appearance acceptance render.
##
## This is evidence plumbing, not an appearance implementation. Every payload
## enters through ElfieActor.configure(), so the render exercises the same
## ActorAppearance material, region, marking, body-scale, and bone-scale path
## used by the world and the adoption preview.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")

const IMAGE_SIZE := Vector2i(512, 512)
const BACKGROUND := Color("707079")
const DEFAULT_OUTPUT_DIR := "/private/tmp/elfienest-appearance-reference/formal-3d"

const ANGLES: Array[Dictionary] = [
	{"id": "front", "position": Vector3(0.0, 0.96, 3.85)},
	{"id": "three_quarter", "position": Vector3(2.55, 1.00, 3.05)},
	{"id": "side", "position": Vector3(3.85, 0.98, 0.0)},
	{"id": "back", "position": Vector3(0.0, 0.96, -3.85)},
]

const LIFE_STAGE_ANGLES: Array[Dictionary] = [
	{"id": "front", "position": Vector3(0.0, 0.96, 3.85)},
	{"id": "three_quarter", "position": Vector3(2.55, 1.00, 3.05)},
	{"id": "side", "position": Vector3(3.85, 0.98, 0.0)},
]

const DOG_VARIANTS: Array[Dictionary] = [
	{
		"id": "dog-01-gray-tuft-ear-crescent",
		"primary": "silver_gray",
		"height_scale": 0.96,
		"build_scale": 0.96,
		"bone_scales": {"HeadScale": 1.06, "NeckLength": 0.97},
		"accents": [
			{"region_id": "head_tuft", "color_id": "honey_gold", "intensity": 0.88},
			{"region_id": "ear_pair", "color_id": "smoky_charcoal", "intensity": 0.78},
		],
		"marking": "crescent",
		"placement": "forehead_center",
		"marking_color": "apricot",
	},
	{
		"id": "dog-02-honey-ear-tip-paws-freckles",
		"primary": "honey_gold",
		"height_scale": 1.02,
		"build_scale": 1.02,
		"bone_scales": {"TailLength": 1.08, "PawScale": 1.06},
		"accents": [
			{"region_id": "ear_tip_pair", "color_id": "silver_gray", "intensity": 0.90},
			{"region_id": "forearm_paw_pair", "color_id": "chocolate", "intensity": 0.82},
		],
		"marking": "freckles",
		"placement": "cheek_pair",
		"marking_color": "russet",
	},
	{
		"id": "dog-03-russet-elbow-knee-heart",
		"primary": "russet",
		"height_scale": 1.00,
		"build_scale": 1.07,
		"bone_scales": {"ArmLength": 0.95, "HandScale": 1.07},
		"accents": [
			{"region_id": "elbow_cuff_pair", "color_id": "ivory", "intensity": 0.92},
			{"region_id": "knee_cuff_pair", "color_id": "silver_gray", "intensity": 0.92},
		],
		"marking": "heart",
		"placement": "chest",
		"marking_color": "honey_gold",
	},
	{
		"id": "dog-04-charcoal-legs-tail-belly-heart",
		"primary": "smoky_charcoal",
		"height_scale": 1.07,
		"build_scale": 0.95,
		"bone_scales": {"LegLength": 1.07, "HeadScale": 0.96},
		"accents": [
			{"region_id": "lower_leg_foot_pair", "color_id": "ivory", "intensity": 0.90},
			{"region_id": "tail_tip", "color_id": "apricot", "intensity": 0.92},
		],
		"marking": "heart",
		"placement": "belly_center",
		"marking_color": "honey_gold",
	},
	{
		"id": "dog-05-apricot-chest-tail-under-star",
		"primary": "apricot",
		"height_scale": 0.98,
		"build_scale": 1.04,
		"bone_scales": {"NeckLength": 0.95, "TailLength": 0.94},
		"accents": [
			{"region_id": "chest_tuft", "color_id": "honey_gold", "intensity": 0.86},
			{"region_id": "tail_underside", "color_id": "chocolate", "intensity": 0.90},
		],
		"marking": "star",
		"placement": "forehead_center",
		"marking_color": "silver_gray",
	},
]

const FOX_VARIANTS: Array[Dictionary] = [
	{
		"id": "fox-01-gray-tuft-ear-crescent",
		"primary": "silver_gray",
		"height_scale": 0.96,
		"build_scale": 0.96,
		"bone_scales": {"HeadScale": 1.05, "NeckLength": 0.97},
		"accents": [
			{"region_id": "head_tuft", "color_id": "golden", "intensity": 0.88},
			{"region_id": "ear_pair", "color_id": "smoky_black", "intensity": 0.78},
		],
		"marking": "crescent",
		"placement": "forehead_center",
		"marking_color": "orange_red",
	},
	{
		"id": "fox-02-golden-ear-tip-paws-freckles",
		"primary": "golden",
		"height_scale": 1.02,
		"build_scale": 1.01,
		"bone_scales": {"TailLength": 1.10, "PawScale": 1.05},
		"accents": [
			{"region_id": "ear_tip_pair", "color_id": "silver_gray", "intensity": 0.90},
			{"region_id": "forearm_paw_pair", "color_id": "sable_brown", "intensity": 0.82},
		],
		"marking": "freckles",
		"placement": "cheek_pair",
		"marking_color": "fox_red",
	},
	{
		"id": "fox-03-red-elbow-knee-heart",
		"primary": "fox_red",
		"height_scale": 1.00,
		"build_scale": 1.06,
		"bone_scales": {"ArmLength": 0.95, "HandScale": 1.06},
		"accents": [
			{"region_id": "elbow_cuff_pair", "color_id": "ivory", "intensity": 0.92},
			{"region_id": "knee_cuff_pair", "color_id": "silver_gray", "intensity": 0.92},
		],
		"marking": "heart",
		"placement": "chest",
		"marking_color": "golden",
	},
	{
		"id": "fox-04-black-legs-tail-belly-heart",
		"primary": "smoky_black",
		"height_scale": 1.07,
		"build_scale": 0.95,
		"bone_scales": {"LegLength": 1.07, "HeadScale": 0.96},
		"accents": [
			{"region_id": "lower_leg_foot_pair", "color_id": "ivory", "intensity": 0.90},
			{"region_id": "tail_tip", "color_id": "orange_red", "intensity": 0.92},
		],
		"marking": "heart",
		"placement": "belly_center",
		"marking_color": "golden",
	},
	{
		"id": "fox-05-champagne-chest-tail-under-star",
		"primary": "champagne",
		"height_scale": 0.98,
		"build_scale": 1.04,
		"bone_scales": {"NeckLength": 0.95, "TailLength": 0.93},
		"accents": [
			{"region_id": "chest_tuft", "color_id": "golden", "intensity": 0.86},
			{"region_id": "tail_underside", "color_id": "sable_brown", "intensity": 0.90},
		],
		"marking": "star",
		"placement": "forehead_center",
		"marking_color": "silver_gray",
	},
]

var _output_dir := DEFAULT_OUTPUT_DIR
var _species_filter := ""
var _candidate_limit := 5
var _life_stage_payload: Dictionary = {}


func _init() -> void:
	var configured_output := OS.get_environment("APPEARANCE_CANDIDATE_OUTPUT")
	if not configured_output.is_empty():
		_output_dir = configured_output
	_species_filter = OS.get_environment("APPEARANCE_CANDIDATE_SPECIES")
	var life_stage_payload_path := OS.get_environment("APPEARANCE_LIFE_STAGE_PAYLOAD")
	if not life_stage_payload_path.is_empty():
		var payload_file := FileAccess.open(life_stage_payload_path, FileAccess.READ)
		if payload_file == null:
			push_error("Unable to read APPEARANCE_LIFE_STAGE_PAYLOAD")
			quit(1)
			return
		var parsed_payload: Variant = JSON.parse_string(payload_file.get_as_text())
		payload_file.close()
		if not parsed_payload is Dictionary:
			push_error("APPEARANCE_LIFE_STAGE_PAYLOAD must contain a JSON object")
			quit(1)
			return
		_life_stage_payload = parsed_payload as Dictionary
	var configured_limit := OS.get_environment("APPEARANCE_CANDIDATE_LIMIT")
	if not configured_limit.is_empty():
		_candidate_limit = clampi(int(configured_limit), 1, 5)
	call_deferred("_render")


func _render() -> void:
	DirAccess.make_dir_recursive_absolute(_output_dir)
	var plates: Array[Image] = []
	if _species_filter.is_empty() or _species_filter == "dog":
		var dog_plate := await _render_species("dog", DOG_SCENE, DOG_VARIANTS)
		dog_plate.save_png("%s/dog-formal-candidates-4views.png" % _output_dir)
		plates.append(dog_plate)
	if _species_filter.is_empty() or _species_filter == "fox":
		var fox_plate := await _render_species("fox", FOX_SCENE, FOX_VARIANTS)
		fox_plate.save_png("%s/fox-formal-candidates-4views.png" % _output_dir)
		plates.append(fox_plate)
	if plates.is_empty():
		push_error("Unknown APPEARANCE_CANDIDATE_SPECIES: %s" % _species_filter)
		quit(1)
		return
	_join_vertical(plates).save_png("%s/formal-candidates-4views.png" % _output_dir)
	_write_catalog()
	if _life_stage_payload.size() > 0:
		if _species_filter.is_empty() or _species_filter == "dog":
			await _write_life_stage_plate("dog", DOG_SCENE)
		if _species_filter.is_empty() or _species_filter == "fox":
			await _write_life_stage_plate("fox", FOX_SCENE)
	print("APPEARANCE_FORMAL_3D_OUTPUT: %s" % _output_dir)
	print(
		"APPEARANCE_FORMAL_3D_CANDIDATES: species=%s count=%d views=front,three_quarter,side,back"
		% [_species_filter if not _species_filter.is_empty() else "dog,fox", _candidate_limit]
	)
	quit()


func _render_species(
	species_id: String,
	scene: PackedScene,
	variants: Array[Dictionary],
) -> Image:
	var rows: Array[Image] = []
	for angle: Dictionary in ANGLES:
		var cells: Array[Image] = []
		for variant: Dictionary in variants.slice(0, _candidate_limit):
			print(
				"APPEARANCE_FORMAL_3D_RENDERING: %s %s %s"
				% [species_id, String(variant["id"]), String(angle["id"])]
			)
			var image := await _render_actor(
				species_id,
				scene,
				variant,
				angle["position"] as Vector3,
			)
			image.save_png(
				"%s/%s-%s.png" % [_output_dir, String(variant["id"]), String(angle["id"])]
			)
			cells.append(image)
		rows.append(_join_horizontal(cells))
	return _join_vertical(rows)


func _write_life_stage_plate(species_id: String, scene: PackedScene) -> void:
	var stage_rows: Variant = _life_stage_payload.get(species_id, [])
	if not stage_rows is Array or (stage_rows as Array).is_empty():
		push_error("Life-stage payload missing stages for %s" % species_id)
		return
	var rows: Array[Image] = []
	for stage_value: Variant in stage_rows as Array:
		if not stage_value is Dictionary:
			push_error("Invalid life-stage entry for %s" % species_id)
			return
		var stage := stage_value as Dictionary
		var stage_id := String(stage.get("stage", ""))
		var age_years := int(stage.get("age_years", -1))
		var cells: Array[Image] = []
		for angle: Dictionary in LIFE_STAGE_ANGLES:
			var view_id := String(angle["id"])
			var image := await _render_actor(
				species_id,
				scene,
				stage,
				angle["position"] as Vector3,
			)
			image.save_png(
				"%s/%s-stage-%s-age-%02d-%s.png"
				% [_output_dir, species_id, stage_id, age_years, view_id]
			)
			cells.append(image)
		rows.append(_join_horizontal(cells))
	_join_vertical(rows).save_png("%s/%s-life-stage-appearance.png" % [_output_dir, species_id])
	_write_life_stage_catalog(species_id, stage_rows as Array)


func _write_life_stage_catalog(species_id: String, stage_rows: Array) -> void:
	var catalog := FileAccess.open(
		"%s/%s-life-stage-appearance.json" % [_output_dir, species_id],
		FileAccess.WRITE,
	)
	if catalog == null:
		push_error("Unable to write life-stage catalog for %s" % species_id)
		return
	var stage_order: Array[String] = []
	var ages_and_stages: Array[Dictionary] = []
	for stage_value: Variant in stage_rows:
		if not stage_value is Dictionary:
			continue
		var stage := stage_value as Dictionary
		stage_order.append(String(stage.get("stage", "")))
		ages_and_stages.append(
			{"stage": stage.get("stage"), "age_years": stage.get("age_years")}
		)
	var catalog_document := {
		"schema": "appearance-life-stage-render.v1",
		"source": "GenesisEngine.generate_appearance -> AppearanceResolver.resolve_genome -> ElfieActor.configure",
		"views_per_stage": ["front", "three_quarter", "side"],
		"stage_order": stage_order,
		"ages_and_stages": ages_and_stages,
	}
	catalog.store_string(JSON.stringify(catalog_document, "\t"))
	catalog.close()


func _render_actor(
	species_id: String,
	scene: PackedScene,
	variant: Dictionary,
	camera_position: Vector3,
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
	camera.position = camera_position
	camera.fov = 36.0
	world.add_child(camera)
	camera.look_at(Vector3(0.0, 0.88, 0.0), Vector3.UP)
	camera.current = true

	var actor := scene.instantiate() as ElfieActor
	actor.install_shared_animations = false
	world.add_child(actor)
	await process_frame
	var appearance_payload: Dictionary = variant.get("appearance", _appearance_payload(variant))
	actor.configure(
		"formal-%s-%s" % [species_id, String(variant.get("id", "life-stage"))],
		Vector3.ZERO,
		appearance_payload,
	)

	for _frame_index in range(5):
		await process_frame
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


func _appearance_payload(variant: Dictionary) -> Dictionary:
	var primary := String(variant["primary"])
	var material_parameters := {
		"palette_id": primary,
		"primary_color_id": primary,
		"marking_id": String(variant.get("marking", "none")),
		"marking_placement": String(variant.get("placement", "none")),
		"marking_color_id": String(variant.get("marking_color", primary)),
		"marking_scale": float(variant.get("marking_scale", 0.90)),
		"marking_intensity": float(variant.get("marking_intensity", 0.92)),
		"region_0_id": "none",
		"region_0_color_id": primary,
		"region_0_intensity": 0.0,
		"region_1_id": "none",
		"region_1_color_id": primary,
		"region_1_intensity": 0.0,
		"region_2_id": "none",
		"region_2_color_id": primary,
		"region_2_intensity": 0.0,
	}
	var accents: Array = variant.get("accents", []) as Array
	for slot in range(mini(accents.size(), 2)):
		var accent := accents[slot] as Dictionary
		material_parameters["region_%d_id" % slot] = String(accent["region_id"])
		material_parameters["region_%d_color_id" % slot] = String(accent["color_id"])
		material_parameters["region_%d_intensity" % slot] = float(accent["intensity"])
	return {
		"height_scale": float(variant.get("height_scale", 1.0)),
		"build_scale": float(variant.get("build_scale", 1.0)),
		"bone_scales": (variant.get("bone_scales", {}) as Dictionary).duplicate(true),
		"blend_shapes": (variant.get("blend_shapes", {}) as Dictionary).duplicate(true),
		"material_parameters": material_parameters,
	}


func _write_catalog() -> void:
	var payload := {
		"schema": "appearance-formal-3d-candidates.v1",
		"source": "ElfieActor.configure -> ActorAppearance.apply",
		"render_mode": "opaque_uv_surface_shader",
		"views": ["front", "three_quarter", "side", "back"],
		"candidate_count": _candidate_limit,
		"species": {"dog": DOG_VARIANTS, "fox": FOX_VARIANTS},
		"constraints": {
			"max_region_accents": 2,
			"max_marks": 1,
			"max_forehead_marks": 1,
			"glb_changed": false,
			"bone_scales_exercised": true,
		},
	}
	var catalog := FileAccess.open("%s/formal-3d-candidate-catalog.json" % _output_dir, FileAccess.WRITE)
	if catalog == null:
		push_error("Unable to write formal 3D candidate catalog")
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
