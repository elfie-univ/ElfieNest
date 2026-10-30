extends SceneTree

const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const SURFACE := preload("res://rooms/estate/estate_surface.gd")
const CONTROL := preload("res://rooms/estate/estate_lighting.gd")
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var estate := load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate() as Node3D
	root.add_child(estate)
	DAYLIGHT.apply(estate)
	var discs := {}
	var rings := {}
	var ceilings := 0
	var linings := 0
	var coves := 0
	var patterned_rugs := 0
	var broad_outputs := {}
	var focused_outputs := {}
	var bedroom_output := 0.0
	var outward_faces := {2: 0, 3: 0}
	var illuminated_faces := {2: 0, 3: 0}
	for light: Light3D in estate.find_children("*", "Light3D", true, false):
		if str(light.name).begins_with("BedroomCeilingM"):
			bedroom_output = maxf(bedroom_output, light.light_energy)
	var nest_state := (load("res://rooms/nest.tscn") as PackedScene).get_state()
	for i in range(nest_state.get_node_count()):
		check(nest_state.get_node_name(i) != &"CeilingFill", "Nest must not contain an artificial ceiling fill")
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		var label := str(extras.get("source_name", mesh.name)).to_lower()
		var module := str(extras.get("module", ""))
		var floor_number := int(extras.get("floor", 1))
		var centre := (mesh.global_transform * mesh.get_aabb()).get_center()
		if module == "central" and floor_number in [2, 3] and extras.get("kind") == "chair":
			var bounds := mesh.global_transform * mesh.get_aabb()
			if bounds.size.x * bounds.size.y * bounds.size.z > 0.1:
				var radial := Vector3(centre.x, 0.0, centre.z - (0.85 if floor_number == 2 else 1.35)).normalized()
				var sample := centre + radial * minf(bounds.size.x, bounds.size.z) * 0.5
				outward_faces[floor_number] += 1
				if reaches_outward_face(estate, mesh, sample, radial): illuminated_faces[floor_number] += 1
		if module == "central" and floor_number in [1, 2, 3]:
			if floor_number == 3 and " downlight " in label and label.ends_with("diffuser"):
				check(mounted_on_ceiling(estate, mesh), "Moved third-floor fixtures must be flush with the real curved ceiling, not suspended in space")
			if floor_number > 1 and ("complete slab" in label or "round arrival floor" in label):
				check((mesh.layers & DAYLIGHT._activity_light_mask({"floor": floor_number - 1})) != 0, "Shared floor slab underside must receive the existing lower-floor fixtures")
			if "circular opal ceiling diffuser" in label:
				discs[floor_number] = centre
				for light: Light3D in mesh.find_children("*", "Light3D", true, false):
					var output := light.light_energy * CONTROL.light_boost(light, CONTROL.lighting_group(light))
					if light is OmniLight3D: broad_outputs[floor_number] = output
					elif light is SpotLight3D: focused_outputs[floor_number] = maxf(float(focused_outputs.get(floor_number, 0.0)), output)
			if "continuous warm diffuser" in label and ("centered ceiling ring" in label or "ceiling ring " in label):
				if not rings.has(floor_number): rings[floor_number] = []
				rings[floor_number].append(centre)
		if module == "central" or module in DAYLIGHT.POD_MODULES:
			var expected := (extras.get("design_lights", []) as Array).size()
			if "five-petal solid opal ceiling lamp" in label: expected += 1
			var actual_lights := mesh.find_children("*", "Light3D", true, false).filter(func(light: Node) -> bool: return light.get_meta("asset_role", "") == "authored-daylight-fixture")
			check(actual_lights.size() == expected, "%s: only the actual designed fixture sources may illuminate the room (%d vs %d)" % [label, actual_lights.size(), expected])
		if module in DAYLIGHT.POD_MODULES and label == "room • structural terrace slab":
			ceilings += 1
			var lower_mask := DAYLIGHT._room_light_mask({"module": module, "floor": 1})
			check((mesh.layers & lower_mask) != 0, "%s ceiling underside must receive its bedroom light" % module)
		if module in DAYLIGHT.POD_MODULES and label.begins_with("room • closed ceiling light"):
			coves += 1
			check(mesh.find_children("BedroomCoveDiffuse*", "Light3D", true, false).is_empty(), "%s must not gain perimeter fill lights" % module)
		if label == "games_front_play_rug":
			patterned_rugs += 1
			check(bool(mesh.mesh.surface_get_format(0) & Mesh.ARRAY_FORMAT_COLOR), "Play rug must retain its authored patchwork colors")
			var material := mesh.get_active_material(0) as ShaderMaterial
			check(material != null and bool(material.get_shader_parameter("use_linear_vertex_color")), "Play rug must display the original patchwork vertex colors")
		if module in DAYLIGHT.POD_MODULES and str(extras.get("piece", "")) in ["inner_wrap", "inner_welt"]:
			linings += 1
			for i in range(mesh.mesh.get_surface_count()):
				var original := mesh.mesh.surface_get_material(i) as BaseMaterial3D
				var actual := mesh.get_active_material(i) as ShaderMaterial
				check(actual != null and actual.shader == SURFACE.OPAQUE, "%s bed lining needs the physical room material path" % module)
				if actual != null:
					check(actual.get_shader_parameter("source_albedo") == original.albedo_color, "Bed lining must retain the authored sage color")
					check(actual.get_shader_parameter("source_normal_texture") == original.normal_texture, "Bed lining must retain the original fabric normal texture")
	for floor_number in [1, 2, 3]:
		var broad := float(broad_outputs.get(floor_number, 0.0))
		check(broad >= float(focused_outputs.get(floor_number, INF)), "L%d broad fixture output must balance its strongest central beam instead of concentrating brightness at the centre" % floor_number)
		check(broad <= bedroom_output * 2.0, "L%d broad fixture output must stay bounded relative to the accepted bedroom fixture" % floor_number)
		check(discs.has(floor_number) and rings.get(floor_number, []).size() == 2, "L%d needs one disc and two central rings" % floor_number)
		for centre: Vector3 in rings.get(floor_number, []):
			var disc: Vector3 = discs.get(floor_number, Vector3.ZERO)
			check(Vector2(centre.x - disc.x, centre.z - disc.z).length() < 0.002, "L%d disc and rings must be coaxial in the actual world transform" % floor_number)
	check(ceilings == 8 and coves == 8 and linings >= 64, "Lighting fix must cover all eight bedrooms and their bed linings")
	check(patterned_rugs == 1, "Review must cover the actual block-play rug")
	for floor_number in [2, 3]:
		check(outward_faces[floor_number] >= 4 and float(illuminated_faces[floor_number]) / outward_faces[floor_number] >= 0.85, "L%d existing ceiling fixtures must reach the outward-facing seating surfaces (%d/%d)" % [floor_number, illuminated_faces[floor_number], outward_faces[floor_number]])
	estate.free()
	for message in failures: push_error(message)
	if failures.is_empty(): print("PASS designed sources only, three concentric ceilings, eight bedrooms and original patchwork rug")
	quit(0 if failures.is_empty() else 1)

func reaches_outward_face(estate: Node3D, receiver: MeshInstance3D, sample: Vector3, normal: Vector3) -> bool:
	var candidates: Array[String] = []
	for light: SpotLight3D in estate.find_children("*", "SpotLight3D", true, false):
		var extras: Dictionary = light.get_parent().get_meta("extras", {})
		if not " downlight " in str(extras.get("source_name", light.get_parent().name)).to_lower(): continue
		if (light.light_cull_mask & receiver.layers) == 0: continue
		var ray := sample - light.global_position
		if normal.dot(-ray.normalized()) > 0.0:
			candidates.append("%s position=%s facing=%.3f angle=%.1f limit=%.1f" % [light.get_parent().name, light.global_position, normal.dot(-ray.normalized()), rad_to_deg(acos(clampf((-light.global_basis.z).dot(ray.normalized()), -1.0, 1.0))), light.spot_angle])
		if ray.length() >= light.spot_range or normal.dot(-ray.normalized()) <= 0.05: continue
		if (-light.global_basis.z).dot(ray.normalized()) >= cos(deg_to_rad(light.spot_angle)): return true
	print("UNCOVERED_SEATING sample=", sample, " normal=", normal, " candidates=", candidates)
	return false

func mounted_on_ceiling(estate: Node3D, fixture: MeshInstance3D) -> bool:
	var up := fixture.global_basis.y.normalized()
	var origin := fixture.global_position - up * 0.02
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if not str(extras.get("source_name", mesh.name)).begins_with("Central L4 round arrival floor"): continue
		for surface in range(mesh.mesh.get_surface_count()):
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			for i in range(0, indices.size(), 3):
				var hit: Variant = Geometry3D.ray_intersects_triangle(origin, up, mesh.global_transform * points[indices[i]], mesh.global_transform * points[indices[i + 1]], mesh.global_transform * points[indices[i + 2]])
				if hit != null and (hit as Vector3).distance_to(fixture.global_position) < 0.03: return true
	return false
