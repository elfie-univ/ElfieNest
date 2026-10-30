extends SceneTree

const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const CONTROL := preload("res://rooms/estate/estate_lighting.gd")
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	for floor_number in [1, 2, 3]:
		var fixture := MeshInstance3D.new()
		fixture.mesh = BoxMesh.new()
		fixture.set_meta("extras", {"module": "central", "floor": floor_number, "source_name": "Working L%d circular opal ceiling diffuser" % floor_number, "design_lights": [{"type": "point", "position": [0, -0.35, 0], "intensity": 1.5, "distance": 4}]})
		world.add_child(fixture)
		DAYLIGHT._restore_fixture_lights(fixture, {})
		var light := fixture.get_child(0) as OmniLight3D
		check(is_equal_approx(light.omni_attenuation, 1.0), "L%d diffuser must retain soft falloff" % floor_number)
		check(is_zero_approx(light.light_specular), "Diffuse ceiling output must not create point highlights")
		var ring := MeshInstance3D.new()
		var shape := BoxMesh.new()
		shape.size = Vector3(6.5, 0.02, 6.5)
		ring.mesh = shape
		ring.position = Vector3(0, floor_number * 3.0, 0)
		ring.set_meta("extras", {"module": "central", "floor": floor_number, "source_name": "L3 ceiling ring 2 continuous warm diffuser" if floor_number == 3 else "L%d ceiling perimeter continuous warm diffuser" % floor_number})
		world.add_child(ring)
		DAYLIGHT._restore_fixture_lights(ring, {})
		check(ring.get_child_count() == 6, "Each outer ceiling band must illuminate all six sectors")
		for source: OmniLight3D in ring.get_children():
			check(source.light_cull_mask == DAYLIGHT.ACTIVITY_LAYERS[floor_number - 1], "Ring output must stay on its own indoor receivers")
			check(source.global_position.y < ring.global_position.y, "Ring emitters must sit below the actual ceiling surface")
			check(Vector2(source.global_position.x, source.global_position.z).length() > 3.0, "Ring output must follow the physical band, not cluster at the room centre")
			check(is_zero_approx(source.light_specular), "Distributed diffuse output must not add point reflections")
		for finish in ["Interior warm plaster", "Exterior • facade", "Observation glass"]:
			var receiver := MeshInstance3D.new()
			receiver.mesh = BoxMesh.new()
			var material := StandardMaterial3D.new()
			material.resource_name = finish
			receiver.mesh.material = material
			receiver.set_meta("extras", {"module": "central", "floor": floor_number, "glass": finish == "Observation glass"})
			world.add_child(receiver)
			DAYLIGHT._calibrate(receiver, {}, {"artificial_surfaces": 0, "sky_meshes": 0, "glass_surfaces": 0, "corrected_surfaces": 0})
			var receives_ceiling: bool = (receiver.layers & int(DAYLIGHT.ACTIVITY_LAYERS[floor_number - 1])) != 0
			check(receives_ceiling == (finish == "Interior warm plaster"), "Ceiling output must reach plaster without lighting exterior shells or glazing")
	var control := CONTROL.new()
	control.bind(world)
	control.apply(false)
	for light: Light3D in world.find_children("*", "Light3D", true, false):
		check(not light.visible, "Ceiling coverage must follow the ordinary light switch")
	control.apply(true, true, PackedStringArray(["central-03"]))
	for light: Light3D in world.find_children("*", "Light3D", true, false):
		check(light.visible == (CONTROL.lighting_group(light) == &"central-03"), "Quiet-hour occupancy must remain floor-specific")
	world.free()
	for message in failures: push_error(message)
	if failures.is_empty(): print("PASS ceiling falloff, distributed coverage, diffuse reflection and floor-specific switching")
	quit(0 if failures.is_empty() else 1)
