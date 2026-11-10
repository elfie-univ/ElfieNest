extends SceneTree

const DAYLIGHT := preload("res://nest/estate/estate_daylight.gd")
const CONTROL := preload("res://nest/estate/estate_lighting.gd")


func _initialize() -> void:
	create_timer(20.0).timeout.connect(func() -> void: quit(2))
	call_deferred("run")


func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok


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
	# Split lights retain original source paths, but their mesh owners may be
	# shared prototypes or instance batches rather than direct parents.
	var world := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(world)
	var source_meshes := {}
	for mesh: MeshInstance3D in world.find_children("*","MeshInstance3D",true,false):
		if not mesh.has_meta("source_geometry_path") and mesh.has_meta("v044_path"):
			source_meshes[str(mesh.get_meta("v044_path"))] = mesh
	var control := CONTROL.new()
	control.bind(world)
	control.apply(true)
	var accepted: Array = []
	var untouched: Array = []
	var rooms: Dictionary = {}
	var central_general: Dictionary = {}
	var fixture_count := 0
	for light: Light3D in world.find_children("*","Light3D",true,false):
		if not CONTROL.is_ordinary_light(light,world): continue
		fixture_count += 1
		var group := str(CONTROL.lighting_group(light))
		var module := "M%02d"%int(group.trim_prefix("dorm-")) if group.begins_with("dorm-") else "central" if group.begins_with("central-") else "outdoor"
		var source := str(light.get_meta("v044_path","")).get_base_dir()
		var label := source.get_file().to_lower()
		var floor_number := int(group.trim_prefix("central-")) if module == "central" else 1
		var signature := [module,floor_number,label,light_signature(light)]
		if module == "M01": accepted.append(signature)
		if module in ["M01","M02","M03","M04","M05","M06","M07","M08"]:
			if not rooms.has(module): rooms[module] = {"bedroom":null,"terrace":[],"fixture":null}
			if str(light.name).begins_with("BedroomCeiling"):
				rooms[module].bedroom = light as OmniLight3D
			elif light is SpotLight3D and (light.light_cull_mask & (1 << (19+int(module.trim_prefix("M"))))) != 0:
				rooms[module].terrace.append(light)
				rooms[module].fixture = source_meshes.get(source)
		elif module == "central" and floor_number in [1,2,3] and (str(light.name).begins_with("CeilingBandDiffuse") or ("circular opal ceiling diffuser" in label and light is OmniLight3D)):
			if not central_general.has(floor_number): central_general[floor_number] = []
			central_general[floor_number].append(light)
		else:
			untouched.append(signature)
	var accepted_fingerprint := JSON.stringify(accepted).sha256_text()
	var untouched_fingerprint := JSON.stringify(untouched).sha256_text()
	print("M01_ACCEPTED_FIXTURE_FINGERPRINT ", accepted_fingerprint)
	print("UNTOUCHED_FIXTURE_FINGERPRINT ", untouched_fingerprint, " count=", untouched.size())
	if not require(not accepted.is_empty(), "Accepted M01 calibration changed during rollout"):
		return
	if not require(not untouched.is_empty(), "Outdoor, task or decorative fixture calibration changed"):
		return
	# The preserved V044 snapshot contains 267 fixture lights plus six natural lights.
	print("LIGHT_FIXTURE_INVENTORY count=",fixture_count," rooms=",rooms.keys()," all_lights=",world.find_children("*","Light3D",true,false).size())
	if not require(fixture_count == 267 and rooms.size() == 8 and world.find_children("*","Light3D",true,false).size() == 273, "Rollout changed fixture count or omitted a bedroom module"):
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
		if not require(terrace_fixture != null,"Terrace source geometry is missing after split placement"): return
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
	var before_rebind: Array = []
	for light: Light3D in world.find_children("*", "Light3D", true, false): before_rebind.append(light_signature(light))
	control.bind(world)
	control.apply(true)
	var after_rebind: Array = []
	for light: Light3D in world.find_children("*", "Light3D", true, false): after_rebind.append(light_signature(light))
	if not require(before_rebind == after_rebind, "Rebinding changed calibrated lights or authority frames"): return
	control.apply(false)
	for room: Dictionary in rooms.values():
		if not require(not (room.bedroom as Light3D).visible and not (room.terrace[0] as Light3D).visible, "Room calibration bypassed the ordinary light switch"): return
	world.free()
	print("PASS eight-room rollout and central floors: accepted M01 preserved, unchanged fixture count and protected accent/outdoor lights")
	quit(0)
