extends SceneTree

const CONTROL := preload("res://rooms/estate/estate_lighting.gd")
const GEOMETRY := preload("res://scripts/tools/outdoor_lighting_geometry.gd")

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var ceiling := MeshInstance3D.new()
	ceiling.mesh = BoxMesh.new()
	ceiling.set_meta("extras", {"module":"central", "floor":3, "source_name":"ceiling ring perimeter diffuser"})
	var material := StandardMaterial3D.new()
	material.resource_name = "Warm ceiling bounce"
	material.emission_enabled = true
	material.emission_energy_multiplier = 0.5
	ceiling.mesh.material = material
	world.add_child(ceiling)
	if not require(CONTROL.lighting_group(ceiling) == &"central-03", "Ceiling rings are room lighting, not quiet-hour safety lighting"):
		return
	var control := CONTROL.new()
	control.bind(world)
	control.apply(false)
	var owned := ceiling.get_active_material(0) as BaseMaterial3D
	if not require(is_zero_approx(owned.emission_energy_multiplier), "Daytime must disable authored wall/ceiling emission too"):
		return
	control.apply(true)
	if not require(owned.emission_energy_multiplier > 0.0, "Evening must retain the original authored emission"):
		return
	control.apply(true, true)
	if not require(is_zero_approx(owned.emission_energy_multiplier), "Unoccupied room ceilings must switch off in quiet hours"):
		return
	var arrival := StandardMaterial3D.new()
	arrival.resource_name = "Roof fine turquoise halo"
	if not require(CONTROL.is_ordinary_emission(arrival), "Idle arrival fixtures must follow the day/quiet switch; event effects own their explicit activation"):
		return
	for file: String in ["res://rooms/estate/estate_opaque.gdshader", "res://runtime/lab/m01_sheen.gdshader"]:
		if not require(not FileAccess.get_file_as_string(file).contains("room_light_scale"), "Room surfaces must receive actual lights without the rejected fixed warm irradiance"):
			return
	var water := PackedVector2Array([Vector2(-2,-2),Vector2(2,-2),Vector2(2,2),Vector2(-2,2)])
	var geometry := GEOMETRY.new()
	var rim: PackedVector3Array = geometry.call("shoreline_rim", water, 0.2)
	if not require(rim.size() >= 5 and rim[0].is_equal_approx(rim[-1]), "Shoreline guidance must form a closed ring"):
		return
	for point in rim:
		if not require(not Geometry2D.is_point_in_polygon(Vector2(point.x, point.z), water), "The lake guidance emitter must sit on the bank, outside the water"):
			return
	world.free()
	print("PASS migrated day/evening/quiet lighting, actual-light receivers and bank-side lake guidance")
	quit(0)
