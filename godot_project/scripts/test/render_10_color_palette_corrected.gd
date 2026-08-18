extends SceneTree

## Corrected phase-1 palette review.
##
## This is the palette review that must be used for the product comparison:
## - it renders the original 3D GLB at three real camera angles;
## - it reuses ActorAppearance.APPEARANCE_SHADER_CODE, including the source
##   fur texture and relative-tone transfer;
## - it does not use the rejected fixed-camera 2D masks;
## - it does not alter the production manifests or GLB files.
##
## The 13-region validator remains a separate evidence plate because a solid
## coat-color review and a local-region boundary review are different tests.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")

const IMAGE_SIZE := Vector2i(256, 256)
const GRID_COLUMNS := 5
const BACKGROUND := Color("707079")
const OUTPUT_RELATIVE := "res://../docs/public/assets/appearance-experiments/phase-1/10-color-palette-corrected"

const ANGLES: Array[Dictionary] = [
	{"id": "front", "position": Vector3(0.0, 0.96, 3.85)},
	{"id": "three_quarter", "position": Vector3(2.55, 1.00, 3.05)},
	{"id": "side", "position": Vector3(3.85, 0.98, 0.0)},
]

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

	await _render_species("dog", DOG_SCENE, DOG_PALETTE)
	await _render_species("fox", FOX_SCENE, FOX_PALETTE)
	print("PALETTE_CORRECTED_EXPERIMENT: dog=10 fox=10 views=front,three_quarter,side")
	print("PALETTE_CORRECTED_RENDER_OUTPUT: %s" % _output_dir)
	quit()


func _render_species(
	species_id: String,
	scene: PackedScene,
	palette: Array[Dictionary],
) -> void:
	var view_grids: Array[Image] = []
	for angle: Dictionary in ANGLES:
		var tiles: Array[Image] = []
		for index in range(palette.size()):
			var item: Dictionary = palette[index]
			var render := await _render_variant(
				scene,
				String(angle["id"]),
				angle["position"] as Vector3,
				item["color"] as Color,
			)
			render.save_png(
				"%s/%s-%s-%02d-%s.png"
				% [_output_dir, species_id, String(angle["id"]), index + 1, String(item["id"])]
			)
			tiles.append(render)
		var grid := _join_grid(tiles, GRID_COLUMNS)
		var grid_path := "%s/%s-10-color-%s.png" % [
			_output_dir,
			species_id,
			String(angle["id"]),
		]
		grid.save_png(grid_path)
		view_grids.append(grid)
	_join_vertical(view_grids).save_png(
		"%s/%s-10-color-3views.png" % [_output_dir, species_id]
	)


func _render_variant(
	scene: PackedScene,
	angle_id: String,
	camera_position: Vector3,
	target_color: Color,
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

	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)
	_apply_saved_color_shader(actor, target_color)

	await process_frame
	await process_frame
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


func _apply_saved_color_shader(actor: Node3D, target_color: Color) -> void:
	var shader := Shader.new()
	shader.code = ACTOR_APPEARANCE.APPEARANCE_SHADER_CODE
	for node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var source_material: Material = mesh_instance.get_active_material(surface_index)
			var material := ShaderMaterial.new()
			material.shader = shader
			# These are the same values used by ActorAppearance for an explicit
			# solid palette slot. No 2D mask or second lighting layer is involved.
			material.set_shader_parameter("base_color", Color.WHITE)
			material.set_shader_parameter("use_base_texture", false)
			material.set_shader_parameter("appearance_tint", Color.WHITE)
			material.set_shader_parameter("use_color_slots", true)
			material.set_shader_parameter("primary_color", target_color)
			material.set_shader_parameter("secondary_color", Color.WHITE)
			material.set_shader_parameter("accent_color", Color.WHITE)
			material.set_shader_parameter("face_mask_color", Color.WHITE)
			material.set_shader_parameter("marking_color", Color("34251f"))
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


func _join_grid(images: Array[Image], columns: int) -> Image:
	var rows := int(ceil(float(images.size()) / float(columns)))
	var output := Image.create(
		IMAGE_SIZE.x * columns,
		IMAGE_SIZE.y * rows,
		false,
		Image.FORMAT_RGBA8,
	)
	output.fill(Color("f2eee7"))
	for index in range(images.size()):
		var x := (index % columns) * IMAGE_SIZE.x
		var y := (index / columns) * IMAGE_SIZE.y
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
