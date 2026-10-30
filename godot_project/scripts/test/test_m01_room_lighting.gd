extends SceneTree

const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const CONTROL := preload("res://rooms/estate/estate_lighting.gd")
# Preserve the accepted M01 sample and all lights outside the approved rollout.
const EXPECTED_M01_FIXTURES := "579e16ad95d735998cec279f98c4ef9ca17743696fdb2f454629b5a551ef853b"
const EXPECTED_UNTOUCHED_FIXTURES := "7cafe6d7e3de5fa4fc4fdb65a48dea6388a48be8feae1002614b985b64fce47e"


func _initialize() -> void:
	create_timer(20.0).timeout.connect(func() -> void: quit(2))
	call_deferred("run")


func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok


func source_fixture(node: Dictionary, document: Dictionary, index: int) -> MeshInstance3D:
	var source: Dictionary = document.meshes[int(node.mesh)].primitives[0]
	var accessor: Dictionary = document.accessors[int(source.attributes.POSITION)]
	var minimum := DAYLIGHT._vector(accessor.min)
	var maximum := DAYLIGHT._vector(accessor.max)
	var box := BoxMesh.new()
	box.size = maximum - minimum
	var arrays := box.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	for vertex in range(vertices.size()):
		vertices[vertex] += (minimum + maximum) * 0.5
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, StandardMaterial3D.new())
	var fixture := MeshInstance3D.new()
	fixture.name = "Fixture_%04d" % index
	fixture.mesh = mesh
	var extras := (node.extras as Dictionary).duplicate(true)
	# Import preserves the glTF node name when source_name is absent.
	if not extras.has("source_name"): extras.source_name = str(node.get("name", ""))
	fixture.set_meta("extras", extras)
	if node.has("matrix"):
		var matrix: Array = node.matrix
		fixture.transform = Transform3D(
			Vector3(matrix[0], matrix[1], matrix[2]),
			Vector3(matrix[4], matrix[5], matrix[6]),
			Vector3(matrix[8], matrix[9], matrix[10]),
			Vector3(matrix[12], matrix[13], matrix[14])
		)
	else:
		fixture.position = DAYLIGHT._vector(node.get("translation", [0, 0, 0]))
		var rotation: Array = node.get("rotation", [0, 0, 0, 1])
		fixture.quaternion = Quaternion(rotation[0], rotation[1], rotation[2], rotation[3])
		fixture.scale = DAYLIGHT._vector(node.get("scale", [1, 1, 1]))
	return fixture


func light_signature(light: Light3D) -> Array:
	var signature: Array = [str(light.name), light.light_color, light.light_energy,
		light.light_specular, light.light_cull_mask, light.shadow_enabled,
		light.shadow_caster_mask, light.global_transform]
	if light is SpotLight3D:
		signature.append_array([light.spot_range, light.spot_angle, light.spot_attenuation, light.spot_angle_attenuation])
	elif light is OmniLight3D:
		signature.append_array([light.omni_range, light.omni_attenuation])
	return signature


func reaches(light: SpotLight3D, point: Vector3) -> bool:
	var offset := point - light.global_position
	return offset.length() < light.spot_range and (-light.global_basis.z).normalized().dot(offset.normalized()) > cos(deg_to_rad(light.spot_angle))


func run() -> void:
	# Read actual fixture metadata/bounds without instantiating the full estate.
	var file := FileAccess.open("res://rooms/estate/ElfieNest-complete-final.glb", FileAccess.READ)
	file.seek(12)
	var length := file.get_32()
	file.get_32()
	var document: Dictionary = JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
	file.close()
	var world := Node3D.new()
	root.add_child(world)
	var fixtures: Array[MeshInstance3D] = []
	for index in range(document.nodes.size()):
		var node: Dictionary = document.nodes[index]
		var extras: Dictionary = node.get("extras", {})
		var label := str(extras.get("source_name", ""))
		if not node.has("mesh") or ((extras.get("design_lights", []) as Array).is_empty() and "five-petal solid opal ceiling lamp" not in label):
			continue
		var fixture := source_fixture(node, document, index)
		world.add_child(fixture)
		fixtures.append(fixture)
	DAYLIGHT.apply(world)
	var control := CONTROL.new()
	control.bind(world)
	control.apply(true)
	var accepted: Array = []
	var untouched: Array = []
	var rooms: Dictionary = {}
	var central_general: Dictionary = {}
	var fixture_count := 0
	for fixture in fixtures:
		var extras: Dictionary = fixture.get_meta("extras")
		var module := str(extras.get("module", ""))
		var label := str(extras.get("source_name", "")).to_lower()
		var floor_number := int(extras.get("floor", 1))
		for light: Light3D in fixture.find_children("*", "Light3D", true, false):
			fixture_count += 1
			var signature := [module, floor_number, label, light_signature(light)]
			if module == "M01": accepted.append(signature)
			if module in ["M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08"]:
				if not rooms.has(module): rooms[module] = {"bedroom": null, "terrace": [], "fixture": null}
				if floor_number == 1:
					rooms[module].bedroom = light as OmniLight3D
				else:
					rooms[module].terrace.append(light as SpotLight3D)
					rooms[module].fixture = fixture
			elif module == "central" and floor_number in [1, 2, 3] and (str(light.name).begins_with("CeilingBandDiffuse") or ("circular opal ceiling diffuser" in label and light is OmniLight3D)):
				if not central_general.has(floor_number): central_general[floor_number] = []
				central_general[floor_number].append(light)
			else:
				untouched.append(signature)
	var accepted_fingerprint := JSON.stringify(accepted).sha256_text()
	var untouched_fingerprint := JSON.stringify(untouched).sha256_text()
	print("M01_ACCEPTED_FIXTURE_FINGERPRINT ", accepted_fingerprint)
	print("UNTOUCHED_FIXTURE_FINGERPRINT ", untouched_fingerprint, " count=", untouched.size())
	if not require(accepted_fingerprint == EXPECTED_M01_FIXTURES, "Accepted M01 calibration changed during rollout"):
		return
	if not require(untouched_fingerprint == EXPECTED_UNTOUCHED_FIXTURES, "Outdoor, task or decorative fixture calibration changed"):
		return
	if not require(fixture_count == 250 and rooms.size() == 8, "Rollout changed fixture count or omitted a bedroom module"):
		return
	var receiver_masks := 0
	for module: String in rooms:
		var bedroom := rooms[module].bedroom as OmniLight3D
		var terrace: Array = rooms[module].terrace
		var terrace_fixture := rooms[module].fixture as MeshInstance3D
		if not require(bedroom != null and terrace.size() == 8, "%s must retain one ceiling and eight terrace sources" % module): return
		if not require(bedroom.light_energy == (rooms.M01.bedroom as OmniLight3D).light_energy and bedroom.light_color == (rooms.M01.bedroom as OmniLight3D).light_color and bedroom.omni_attenuation == 1.0 and bedroom.omni_range == 10.0 and bedroom.light_specular == 0.0, "%s bedroom does not match the accepted warm, diffuse M01 fixture" % module): return
		var bedroom_mask := bedroom.light_cull_mask
		var terrace_mask := (terrace[0] as SpotLight3D).light_cull_mask
		if not require((bedroom_mask & terrace_mask) == 0 and ((bedroom_mask | terrace_mask) & receiver_masks) == 0, "%s lighting overlaps another floor/module's receivers" % module): return
		receiver_masks |= bedroom_mask | terrace_mask
		var centre := terrace_fixture.get_aabb().get_center()
		for local: Vector3 in [Vector3(centre.x, 3.15, centre.z), Vector3(-2.3, 3.65, 0.5), Vector3(2.3, 3.65, 0.5)]:
			var count := 0
			for light: SpotLight3D in terrace:
				if not require(light.light_specular == 0.0 and light.light_color == bedroom.light_color and light.spot_range == 6.5 and light.spot_attenuation == 1.0, "%s terrace differs from the accepted diffuse fixture" % module): return
				if reaches(light, terrace_fixture.global_transform * local): count += 1
			if not require(count >= 2, "%s terrace centre/seating lacks overlapping beams" % module): return
		print("PASS ", module, " bedroom and terrace coverage, warm diffuse fixtures and receiver isolation")
	for floor_number in [1, 2, 3]:
		if not require(central_general.has(floor_number), "Central floor lacks its general ceiling fixtures"): return
		var opal_count := 0
		for light: OmniLight3D in central_general[floor_number]:
			if not require(light.light_specular == 0.0 and light.light_color == (rooms.M01.bedroom as OmniLight3D).light_color, "Central general lighting must stay warm without pinpoint floor reflections"): return
			if str(light.name).begins_with("CeilingBandDiffuse"):
				if not require(light.light_energy >= 2.3, "Central perimeter lighting is below the accepted room visibility target"): return
			else:
				opal_count += 1
				if not require(light.light_energy >= (rooms.M01.bedroom as OmniLight3D).light_energy * 0.8, "Central ceiling diffuse output remains below the M01 reference"): return
		if not require(opal_count > 0, "Central floor has no opal diffuse source"): return
		print("PASS central floor ", floor_number, " warm general ceiling lighting")
	control.apply(false)
	for room: Dictionary in rooms.values():
		if not require(not (room.bedroom as Light3D).visible and not (room.terrace[0] as Light3D).visible, "Room calibration bypassed the ordinary light switch"): return
	world.free()
	print("PASS eight-room rollout and central floors: accepted M01 preserved, unchanged fixture count and protected accent/outdoor lights")
	quit(0)
