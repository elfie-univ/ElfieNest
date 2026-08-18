extends SceneTree

## Phase 1 color-palette feasibility experiment.
##
## This script renders the real dog/fox GLB scenes with the current production
## fur shader and a proposed 10-color coat palette. It is deliberately
## isolated from species manifests: the palette is an experiment, not a
## production color contract.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")

const IMAGE_SIZE := Vector2i(256, 256)
const TILE_SIZE := Vector2i(256, 302)
const GRID_COLUMNS := 5
const BACKGROUND := Color("707079")
const OUTPUT_RELATIVE := "res://../docs/public/assets/appearance-experiments/phase-1/10-color-palette-v2"

const DOG_PALETTE: Array[Dictionary] = [
	{"id": "snow_white", "label": "01 snow_white", "color": Color("efe8dc")},
	{"id": "ivory", "label": "02 ivory", "color": Color("e3cda7")},
	{"id": "cream", "label": "03 cream", "color": Color("d8ad76")},
	{"id": "honey_gold", "label": "04 honey_gold", "color": Color("c9884b")},
	{"id": "apricot", "label": "05 apricot", "color": Color("d77b4d")},
	{"id": "russet", "label": "06 russet", "color": Color("9d4e32")},
	{"id": "chestnut", "label": "07 chestnut", "color": Color("814b34")},
	{"id": "chocolate", "label": "08 chocolate", "color": Color("653b2c")},
	{"id": "silver_gray", "label": "09 silver_gray", "color": Color("7a8288")},
	{"id": "smoky_charcoal", "label": "10 smoky_charcoal", "color": Color("4a4d52")},
]

const FOX_PALETTE: Array[Dictionary] = [
	{"id": "ivory", "label": "01 ivory", "color": Color("e2d3bd")},
	{"id": "cream", "label": "02 cream", "color": Color("d7ae7d")},
	{"id": "champagne", "label": "03 champagne", "color": Color("d8b778")},
	{"id": "golden", "label": "04 golden", "color": Color("c98542")},
	{"id": "orange_red", "label": "05 orange_red", "color": Color("c95a2d")},
	{"id": "fox_red", "label": "06 fox_red", "color": Color("a8442b")},
	{"id": "chestnut", "label": "07 chestnut", "color": Color("713828")},
	{"id": "sable_brown", "label": "08 sable_brown", "color": Color("664233")},
	{"id": "silver_gray", "label": "09 silver_gray", "color": Color("7a8288")},
	{"id": "smoky_black", "label": "10 smoky_black", "color": Color("45474c")},
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

	var dog_grid := await _render_species("dog", DOG_SCENE, DOG_PALETTE)
	var fox_grid := await _render_species("fox", FOX_SCENE, FOX_PALETTE)
	dog_grid.save_png("%s/dog-10-color-palette.png" % _output_dir)
	fox_grid.save_png("%s/fox-10-color-palette.png" % _output_dir)
	var combined := _join_vertical([dog_grid, fox_grid])
	combined.save_png("%s/dog-fox-10-color-palette.png" % _output_dir)

	print("PALETTE_EXPERIMENT: dog=10 fox=10")
	print("PALETTE_RENDER_OUTPUT: %s" % _output_dir)
	quit()


func _render_species(
	species_id: String,
	scene: PackedScene,
	palette: Array[Dictionary],
) -> Image:
	var tiles: Array[Image] = []
	for index in range(palette.size()):
		var item: Dictionary = palette[index]
		var render := await _render_variant(species_id, scene, item["color"] as Color)
		render.save_png(
			"%s/%s-%02d-%s.png" % [_output_dir, species_id, index + 1, String(item["id"])]
		)
		tiles.append(_label_tile(render, String(item["label"])))
	return _join_grid(tiles, GRID_COLUMNS)


func _render_variant(species_id: String, scene: PackedScene, target_color: Color) -> Image:
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

	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)
	_apply_palette_material(actor, species_id, target_color)

	await process_frame
	await process_frame
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


func _apply_palette_material(actor: Node3D, species_id: String, target_color: Color) -> void:
	var shader := Shader.new()
	shader.code = ACTOR_APPEARANCE.APPEARANCE_SHADER_CODE
	var protected_color := Color("f2ede3") if species_id == "dog" else Color("f0ece2")
	for node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var material := ShaderMaterial.new()
			material.shader = shader
			material.set_shader_parameter("base_color", Color.WHITE)
			material.set_shader_parameter("use_base_texture", false)
			material.set_shader_parameter("appearance_tint", Color.WHITE)
			material.set_shader_parameter("use_color_slots", true)
			material.set_shader_parameter("primary_color", target_color)
			material.set_shader_parameter("secondary_color", protected_color)
			material.set_shader_parameter("accent_color", protected_color)
			material.set_shader_parameter("face_mask_color", protected_color)
			material.set_shader_parameter("marking_color", Color("34251f"))
			# This plate isolates the base-coat question. White-region
			# protection is a separate experiment and must not hide the
			# candidate color while we judge its naturalness.
			material.set_shader_parameter("appearance_pattern", 0)
			material.set_shader_parameter("appearance_layout", 0)
			material.set_shader_parameter("appearance_marking", 0)
			material.set_shader_parameter("appearance_marking_placement", 0)
			material.set_shader_parameter("appearance_marking_zone", Vector4.ZERO)
			material.set_shader_parameter("appearance_marking_scale", 0.9)
			material.set_shader_parameter("appearance_marking_intensity", 0.0)
			material.set_shader_parameter("source_detail_strength", 0.92)
			material.set_shader_parameter("source_mid_luma", 0.64)
			material.set_shader_parameter("source_emission_strength", 0.0)

			var source_material: Material = mesh_instance.get_active_material(surface_index)
			var source_texture: Texture2D = null
			if source_material is BaseMaterial3D:
				var base_material := source_material as BaseMaterial3D
				source_texture = base_material.emission_texture
				if source_texture == null:
					source_texture = base_material.albedo_texture
			if source_texture != null:
				material.set_shader_parameter("source_fur_texture", source_texture)
				material.set_shader_parameter("use_source_fur_texture", true)
			else:
				material.set_shader_parameter("use_source_fur_texture", false)
			mesh_instance.set_surface_override_material(surface_index, material)


func _label_tile(image: Image, label: String) -> Image:
	var tile := Image.create(TILE_SIZE.x, TILE_SIZE.y, false, Image.FORMAT_RGBA8)
	tile.fill(Color("f8f5ef"))
	tile.blit_rect(image, Rect2i(Vector2i.ZERO, IMAGE_SIZE), Vector2i.ZERO)
	return tile


func _join_grid(images: Array[Image], columns: int) -> Image:
	var rows := int(ceil(float(images.size()) / float(columns)))
	var output := Image.create(
		TILE_SIZE.x * columns,
		TILE_SIZE.y * rows,
		false,
		Image.FORMAT_RGBA8,
	)
	output.fill(Color("f2eee7"))
	for index in range(images.size()):
		var x := (index % columns) * TILE_SIZE.x
		var y := (index / columns) * TILE_SIZE.y
		output.blit_rect(images[index], Rect2i(Vector2i.ZERO, TILE_SIZE), Vector2i(x, y))
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
