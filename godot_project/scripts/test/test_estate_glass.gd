extends SceneTree

const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var fixture := Node3D.new()
	root.add_child(fixture)
	var original := StandardMaterial3D.new()
	original.resource_name = "Trial ice-aqua skylight with restrained thin-film reflection"
	original.albedo_color = Color(0.8, 0.95, 1.0)
	original.roughness = 0.012
	original.set_meta("source_optics", {"transmission": 0.94, "ior": 1.46, "clearcoat": 0.4, "clearcoat_roughness": 0.045})
	original.set_meta("m01_reference_optics", {"extensions": {"KHR_materials_volume": {"thicknessFactor": 0.008, "attenuationDistance": 2.5, "attenuationColor": [0.92, 0.985, 1.0]}}})
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	mesh.mesh.material = original
	mesh.set_meta("extras", {"module": "central", "floor": 4, "glass": true, "roof_skylight": true})
	fixture.add_child(mesh)
	DAYLIGHT.apply(fixture)
	var actual := mesh.get_active_material(0) as ShaderMaterial
	if actual == null:
		push_error("Skylight still scales reflection by transmission alpha")
		quit(1)
		return
	if actual.shader.get_shader_uniform_list().is_empty():
		push_error("Skylight shader did not compile")
		quit(1)
		return
	if actual.get_shader_parameter("source_albedo") != original.albedo_color or not is_equal_approx(float(actual.get_shader_parameter("source_transmission")), 0.94) or not is_equal_approx(float(actual.get_shader_parameter("source_ior")), 1.46) or not is_equal_approx(float(actual.get_shader_parameter("source_roughness")), original.roughness):
		push_error("Skylight lost authored RGB, roughness, transmission or IOR")
		quit(1)
		return
	if original.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED or original.albedo_color.a != 1.0:
		push_error("Skylight mutated the imported source material")
		quit(1)
		return
	if not is_equal_approx(float(actual.get_shader_parameter("source_thickness")), 0.008) or not is_equal_approx(float(actual.get_shader_parameter("source_attenuation_distance")), 2.5):
		push_error("Skylight volume lost its authored thickness or attenuation distance")
		quit(1)
		return
	print("PASS: screen transmission, Fresnel reflection and source volume optics retained")
	fixture.free()
	quit(0)
