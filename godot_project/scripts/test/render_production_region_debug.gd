extends SceneTree

## Formal region comparison render.
##
## This delegates region classification to ActorAppearance's production shader
## and renders the frozen 13 regions in four views. It is the sole replayable
## region-baseline renderer; historical discovery shaders are not duplicated.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")
const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")

const IMAGE_SIZE := Vector2i(512, 512)
const BACKGROUND := Color("2a2a31")
const DEFAULT_OUTPUT_DIR := "/private/tmp/elfienest-appearance-reference/formal-regions"

const ANGLES: Array[Dictionary] = [
	{"id": "front", "position": Vector3(0.0, 0.96, 3.85)},
	{"id": "three_quarter", "position": Vector3(2.55, 1.00, 3.05)},
	{"id": "side", "position": Vector3(3.85, 0.98, 0.0)},
	{"id": "top", "position": Vector3(0.0, 4.10, 0.0), "up": Vector3(0.0, 0.0, -1.0)},
]

const REGION_KEYS: Array[String] = [
	"head_tuft",
	"forehead_mark_zone",
	"ear_pair",
	"ear_tip_pair",
	"cheek_fluff",
	"chest_tuft",
	"belly_center",
	"forearm_paw_pair",
	"elbow_cuff_pair",
	"lower_leg_foot_pair",
	"knee_cuff_pair",
	"tail_tip",
	"tail_underside",
]

const REGION_COLORS: Array[Color] = [
	Color("00e5ff"),
	Color("d500f9"),
	Color("ffe600"),
	Color("76ff03"),
	Color("00c853"),
	Color("ff00aa"),
	Color("2962ff"),
	Color("7c4dff"),
	Color("ff1744"),
	Color("ff4081"),
	Color("00b8d4"),
	Color("c6ff00"),
	Color("37474f"),
]

var _output_dir := DEFAULT_OUTPUT_DIR


func _init() -> void:
	var configured_output := OS.get_environment("APPEARANCE_FORMAL_REGION_OUTPUT")
	if not configured_output.is_empty():
		_output_dir = configured_output
	call_deferred("_render")


func _render() -> void:
	DirAccess.make_dir_recursive_absolute(_output_dir)
	var dog_grid := await _render_species("dog", DOG_SCENE)
	var fox_grid := await _render_species("fox", FOX_SCENE)
	dog_grid.save_png("%s/dog-formal-region-grid-4views.png" % _output_dir)
	fox_grid.save_png("%s/fox-formal-region-grid-4views.png" % _output_dir)
	_join_vertical([dog_grid, fox_grid]).save_png(
		"%s/dog-fox-formal-region-grid-4views.png" % _output_dir
	)
	_write_catalog()
	print("APPEARANCE_FORMAL_REGION_OUTPUT: %s" % _output_dir)
	print("APPEARANCE_FORMAL_REGIONS: dog=13 fox=13 views=front,three_quarter,side,top")
	quit()


func _render_species(species_id: String, scene: PackedScene) -> Image:
	var rows: Array[Image] = []
	for region_id in range(REGION_KEYS.size()):
		var views: Array[Image] = []
		for angle: Dictionary in ANGLES:
			var image := await _render_scene(
				species_id,
				scene,
				angle,
				region_id,
			)
			image.save_png(
				"%s/%s-region-%02d-%s-%s.png"
				% [_output_dir, species_id, region_id, REGION_KEYS[region_id], String(angle["id"])]
			)
			views.append(image)
		var row := _join_horizontal(views)
		row.save_png(
			"%s/%s-region-%02d-%s-4views.png"
			% [_output_dir, species_id, region_id, REGION_KEYS[region_id]]
		)
		rows.append(row)
	return _join_vertical(rows)


func _render_scene(
	species_id: String,
	scene: PackedScene,
	angle: Dictionary,
	selected_region: int,
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
	camera.position = angle["position"] as Vector3
	camera.fov = 36.0
	world.add_child(camera)
	var camera_up: Vector3 = angle.get("up", Vector3.UP)
	camera.look_at(Vector3(0.0, 0.88, 0.0), camera_up)
	camera.current = true

	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)
	var visual_root := actor.get_node_or_null("VisualRoot") as Node3D
	if visual_root == null:
		push_error("Actor scene is missing VisualRoot: %s" % species_id)
		viewport.queue_free()
		await process_frame
		return Image.create(IMAGE_SIZE.x, IMAGE_SIZE.y, false, Image.FORMAT_RGBA8)
	ACTOR_APPEARANCE.apply_region_debug(
		visual_root,
		species_id,
		selected_region,
		REGION_COLORS[selected_region],
	)

	await process_frame
	await process_frame
	await process_frame
	await process_frame
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


func _write_catalog() -> void:
	var rows: Array[Dictionary] = []
	for index in range(REGION_KEYS.size()):
		rows.append({
			"id": index,
			"key": REGION_KEYS[index],
			"color": "#%s" % REGION_COLORS[index].to_html(false),
		})
	var payload := {
		"schema": "appearance-formal-region-grid.v1",
		"selection": "selected_region overrides classify_region; overlap priority comes from ActorAppearance",
		"runtime_source": "res://runtime/actor/actor_appearance.gd",
		"views": ["front", "three_quarter", "side", "top"],
		"regions": rows,
	}
	var catalog := FileAccess.open("%s/formal-region-catalog.json" % _output_dir, FileAccess.WRITE)
	if catalog == null:
		push_error("Unable to write formal region catalog")
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
		output.blit_rect(image, Rect2i(Vector2i.ZERO, image.get_size()), Vector2i(0, y_offset))
		y_offset += image.get_height()
	return output
