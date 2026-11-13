extends SceneTree

class Preview extends "res://tools/static_asset_review.gd":
	func _ready() -> void:
		pass

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var view := Preview.new()
	view.camera = Camera3D.new()
	view.light = DirectionalLight3D.new()
	view.light.light_energy = 1.25
	view.ambient = WorldEnvironment.new()
	view.ambient.environment = Environment.new()
	view.ambient.environment.ambient_light_energy = 0.7
	view.add_child(view.camera)
	view.add_child(view.light)
	view.add_child(view.ambient)
	root.add_child(view)
	view.previews = {
		"source:central-building": {"path": "res://nest/buildings/main/central-building.glb", "source": true},
		"source:pod-building": {"path": "res://nest/buildings/pod/pod-building.glb", "source": true},
	}
	if not require(view.show_scene("source:central-building") > 0, "Main building must load for preview"):
		return
	if not require(view.light.light_energy < 1.25 and view.ambient.environment.ambient_light_energy < 0.7, "Main building must have a softer isolated preview light"):
		return
	var skylight: MeshInstance3D
	for mesh: MeshInstance3D in view.current.find_children("*", "MeshInstance3D", true, false):
		if mesh.get_meta("extras", {}).get("source_name") == "Central integrated shallow skylight": skylight = mesh
	var glass := skylight.get_active_material(0) as ShaderMaterial if skylight != null else null
	if not require(glass != null and glass.shader == preload("res://nest/rendering/estate_glass.gdshader"), "Isolated skylight must use the assembly transmission shader"):
		return
	if not require(is_equal_approx(glass.get_shader_parameter("source_transmission"), 0.94), "Skylight must retain authored transmission"):
		return
	if not require(view.ambient.environment.tonemap_mode == Environment.TONE_MAPPER_ACES and is_equal_approx(view.ambient.environment.tonemap_exposure, 0.88), "Preview must use the exposure assumed by the screen-transmission shader"):
		return
	if not require(view.show_scene("source:pod-building") > 0, "Bedroom building must load for preview"):
		return
	if not require(is_equal_approx(view.light.light_energy, 1.25) and is_equal_approx(view.ambient.environment.ambient_light_energy, 0.7), "Main building calibration must not leak to other assets"):
		return
	if not require(view.ambient.environment.sky == null and view.ambient.environment.tonemap_mode == Environment.TONE_MAPPER_LINEAR, "Main building glass environment must not leak to other assets"):
		return
	view.free()
	print("PASS main building preview light is isolated")
	quit(0)
