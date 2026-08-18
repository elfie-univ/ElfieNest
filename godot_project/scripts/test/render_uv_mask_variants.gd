extends SceneTree

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const IMAGE_SIZE := Vector2i(512, 512)
const OUTPUT_DIR := "/private/tmp/elfienest-appearance-reference/algorithm/uv-mask-v1"
const COLORS := {
	"dog": ["original", "gray", "cream", "chocolate"],
	"fox": ["original", "silver", "pale", "cross"],
}
const MASK_DEBUG_SHADER := """
shader_type spatial;
render_mode unshaded;

uniform sampler2D debug_mask : source_color;
uniform int debug_channel = 0;
uniform bool show_source = false;
uniform sampler2D source_texture : source_color;

void fragment() {
    vec3 output_color = vec3(0.0);
    if (show_source) {
        output_color = texture(source_texture, UV).rgb;
    } else {
        vec4 mask = texture(debug_mask, UV);
        float value = debug_channel == 0 ? mask.r : mask.g;
        output_color = vec3(value);
    }
    ALBEDO = output_color;
}
"""


func _init() -> void:
	call_deferred("_render")


func _render() -> void:
	DirAccess.make_dir_recursive_absolute(OUTPUT_DIR)
	for species_id: String in ["dog", "fox"]:
		var variants: Array[Image] = []
		for color_id: String in COLORS[species_id]:
			var image := await _render_variant(species_id, color_id)
			variants.append(image)
			image.save_png("%s/%s-%s.png" % [OUTPUT_DIR, species_id, color_id])
		var row := _join_horizontal(variants)
		row.save_png("%s/%s-matrix.png" % [OUTPUT_DIR, species_id])
		print("Rendered UV mask matrix: %s" % species_id)
	var combined := _join_vertical([
		_load_image("%s/dog-matrix.png" % OUTPUT_DIR),
		_load_image("%s/fox-matrix.png" % OUTPUT_DIR),
	])
	combined.save_png("%s/dog-fox-uv-mask-matrix.png" % OUTPUT_DIR)
	var fox_side := await _render_variant("fox", "cross", Vector3(3.85, 0.96, 0.10))
	fox_side.save_png("%s/fox-cross-side.png" % OUTPUT_DIR)
	var dog_face := await _render_variant("dog", "chocolate")
	dog_face.save_png("%s/dog-chocolate-face.png" % OUTPUT_DIR)
	var fox_white_mask := await _render_mask_debug("fox", 1)
	fox_white_mask.save_png("%s/fox-white-mask-projection.png" % OUTPUT_DIR)
	var fox_source := await _render_mask_debug("fox", 1, true)
	fox_source.save_png("%s/fox-source-projection.png" % OUTPUT_DIR)
	print("Saved UV mask comparison: %s/dog-fox-uv-mask-matrix.png" % OUTPUT_DIR)
	quit()


func _render_variant(species_id: String, color_id: String, camera_position := Vector3(0.0, 0.96, 3.85)) -> Image:
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
	environment_resource.background_color = Color("707079")
	environment_resource.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment_resource.ambient_light_color = Color.WHITE
	environment_resource.ambient_light_energy = 1.2
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
	var scene: PackedScene = DOG_SCENE if species_id == "dog" else FOX_SCENE
	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)
	if color_id != "original":
		var visual_root := actor.get_node_or_null("VisualRoot") as Node3D
		var collision_shape := actor.get_node_or_null("CollisionShape3D") as CollisionShape3D
		if visual_root != null and collision_shape != null:
			ACTOR_APPEARANCE.apply(
				visual_root,
				collision_shape,
				{"material_parameters": _appearance_parameters(species_id, color_id)},
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


func _appearance_parameters(species_id: String, palette_id: String) -> Dictionary:
	var secondary := "silver" if species_id == "fox" else "white"
	return {
		"palette_id": palette_id,
		"pattern_id": "solid" if species_id == "dog" else "classic",
		"pattern_layout_id": "solid" if species_id == "dog" else "classic",
		"primary_color_id": palette_id,
		"secondary_color_id": secondary,
		"accent_color_id": secondary,
		"face_mask_color_id": secondary,
		"marking_color_id": secondary,
		"marking_id": "none",
		"marking_placement": "none",
		"marking_scale": 0.9,
		"marking_intensity": 0.0,
	}


func _render_mask_debug(species_id: String, channel: int, show_source := false) -> Image:
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
	environment_resource.background_color = Color("707079")
	environment.environment = environment_resource
	world.add_child(environment)
	var camera := Camera3D.new()
	camera.position = Vector3(0.0, 0.96, 3.85)
	camera.fov = 36.0
	world.add_child(camera)
	camera.look_at(Vector3(0.0, 0.88, 0.0), Vector3.UP)
	camera.current = true
	var scene: PackedScene = DOG_SCENE if species_id == "dog" else FOX_SCENE
	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)
	var mask: Texture2D = preload("res://characters/dog/dog_appearance_masks.png") if species_id == "dog" else preload("res://characters/fox/fox_appearance_masks.png")
	var shader := Shader.new()
	shader.code = MASK_DEBUG_SHADER
	for node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var material := ShaderMaterial.new()
			material.shader = shader
			material.set_shader_parameter("debug_mask", mask)
			material.set_shader_parameter("debug_channel", channel)
			if show_source:
				material.set_shader_parameter("show_source", true)
				material.set_shader_parameter("source_texture", preload("res://characters/fox/fox_shaded.png") if species_id == "fox" else preload("res://characters/dog/dog_shaded.png"))
			mesh_instance.set_surface_override_material(surface_index, material)
	await process_frame
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


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
	for index in range(images.size()):
		var image := images[index]
		var size := image.get_size()
		output.blit_rect(image, Rect2i(Vector2i.ZERO, size), Vector2i(0, y_offset))
		y_offset += size.y
	return output


func _load_image(path: String) -> Image:
	var image := Image.load_from_file(path)
	return image if image != null else Image.create(IMAGE_SIZE.x * 4, IMAGE_SIZE.y, false, Image.FORMAT_RGBA8)
