extends SceneTree

const DAYLIGHT := preload("res://nest/estate/estate_daylight.gd")
const SURFACE := preload("res://nest/estate/estate_surface.gd")
const CONTROL := preload("res://nest/estate/estate_lighting.gd")
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var estate := load("res://nest/estate/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var exterior_camera := Vector3(21, 17, 28)
	var exterior_spots := 0
	for light: SpotLight3D in estate.find_children("*", "SpotLight3D", true, false):
		if not light.is_visible_in_tree(): continue
		var fade_end := light.distance_fade_begin + light.distance_fade_length
		if not light.distance_fade_enabled or light.global_position.distance_to(exterior_camera) <= fade_end:
			exterior_spots += 1
	check(exterior_spots <= 16384 / 112, "The actual composed exterior must fit the minimum WebGL spot buffer, including outdoor fixtures, so ceiling beams are never discarded")
	check_interior_light_budget(estate)
	var discs := {}
	var rings := {}
	var ceilings := 0
	var facade_panes := 0
	var linings := 0
	var coves := 0
	var patterned_rugs := 0
	var broad_outputs := {}
	var focused_outputs := {}
	var overlapping_outputs := {}
	var bedroom_output := 0.0
	var daybed_backs := 0
	var front_fixture_parts := 0
	var outward_faces := {2: 0, 3: 0}
	var illuminated_faces := {2: 0, 3: 0}
	for light: Light3D in estate.find_children("*", "Light3D", true, false):
		if str(light.name).begins_with("BedroomCeilingM"):
			bedroom_output = maxf(bedroom_output, light.light_energy)
	var nest_state := (load("res://nest/nest.tscn") as PackedScene).get_state()
	for i in range(nest_state.get_node_count()):
		check(nest_state.get_node_name(i) != &"CeilingFill", "Nest must not contain an artificial ceiling fill")
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		var label := str(extras.get("source_name", mesh.name)).to_lower()
		var module := str(extras.get("module", ""))
		var floor_number := int(extras.get("floor", 1))
		var centre := (mesh.global_transform * mesh.get_aabb()).get_center()
		if module == "central" and floor_number == 3 and label == "quiet_front_sage_daybed":
			var bounds := mesh.global_transform * mesh.get_aabb()
			var back := Vector3(bounds.get_center().x, bounds.position.y + 0.06, bounds.end.z - 0.18)
			daybed_backs += 1
			check(reaches_outward_face(estate, mesh, back, Vector3(0.0, -0.12, 1.0).normalized()), "The front window daybed's downward-tilted back must receive a real existing ceiling beam")
		if module == "central" and floor_number == 3 and label.begins_with("working l3 downlight 1 "):
			front_fixture_parts += 1
			check(mounted_on_ceiling(estate, mesh), "The moved diffuser, rim and baffle must all remain mounted on the actual ceiling")
		if module == "central":
			for surface in range(mesh.mesh.get_surface_count()):
				var original := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
				if original == null or original.resource_name.to_lower() != "trial nearly clear ice-aqua facade glass": continue
				facade_panes += 1
				var pane := mesh.get_active_material(surface) as BaseMaterial3D
				check(pane != null and is_equal_approx(1.0 - pow(1.0 - pane.albedo_color.a, 2.0), original.albedo_color.a), "Both faces of a facade pane must preserve the authored whole-pane opacity without darkening the room twice")
		if module == "central" and floor_number in [2, 3] and extras.get("kind") == "chair":
			var bounds := mesh.global_transform * mesh.get_aabb()
			if bounds.size.x * bounds.size.y * bounds.size.z > 0.1:
				var radial := Vector3(centre.x, 0.0, centre.z - (0.85 if floor_number == 2 else 1.35)).normalized()
				var sample := centre + radial * minf(bounds.size.x, bounds.size.z) * 0.5
				outward_faces[floor_number] += 1
				if reaches_outward_face(estate, mesh, sample, radial): illuminated_faces[floor_number] += 1
		if module == "central" and floor_number in [2, 3, 4] and ("complete slab" in label or "round arrival floor" in label):
			check((mesh.layers & DAYLIGHT._activity_light_mask({"floor": floor_number - 1})) != 0, "L%d shared slab underside must receive the existing lower-floor fixtures" % floor_number)
		if module == "central" and floor_number in [1, 2, 3]:
			if floor_number == 3 and " downlight " in label and label.ends_with("diffuser"):
				check(mounted_on_ceiling(estate, mesh), "Moved third-floor fixtures must be flush with the real curved ceiling, not suspended in space")
			if "circular opal ceiling diffuser" in label:
				discs[floor_number] = centre
				for light: Light3D in mesh.find_children("*", "Light3D", true, false):
					var output := light.light_energy * CONTROL.light_boost(light, CONTROL.lighting_group(light))
					if light is OmniLight3D: broad_outputs[floor_number] = output
					elif light is SpotLight3D:
						focused_outputs[floor_number] = maxf(float(focused_outputs.get(floor_number, 0.0)), output)
						if (light as SpotLight3D).spot_angle > 57.0:
							overlapping_outputs[floor_number] = float(overlapping_outputs.get(floor_number, 0.0)) + output
			if "continuous warm diffuser" in label and ("centered ceiling ring" in label or "ceiling ring " in label):
				if not rings.has(floor_number): rings[floor_number] = []
				rings[floor_number].append(centre)
		if module == "central" or module in DAYLIGHT.POD_MODULES:
			var expected := (extras.get("design_lights", []) as Array).size()
			if "five-petal solid opal ceiling lamp" in label: expected += 1
			var actual_lights := mesh.find_children("*", "Light3D", true, false).filter(func(light: Node) -> bool: return light.get_meta("asset_role", "") == "authored-daylight-fixture")
			check(actual_lights.size() == expected, "%s: only the actual designed fixture sources may illuminate the room (%d vs %d)" % [label, actual_lights.size(), expected])
			if module == "central" and floor_number in [1, 2, 3] and "circular opal ceiling diffuser" not in label and " downlight " not in label:
				for light: Light3D in actual_lights:
					check((light.light_cull_mask & DAYLIGHT._activity_light_mask(extras)) == 0, "Local task and accent lamps must not become general furniture fill lights")
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
		check(broad + float(overlapping_outputs.get(floor_number, INF)) <= bedroom_output * 3.0, "L%d central fixture must budget its diffuse and overlapping beam outputs together" % floor_number)
		check(float(overlapping_outputs.get(floor_number, INF)) <= bedroom_output * 2.0, "L%d overlapping central beams must be bounded together, not just individually" % floor_number)
		check(discs.has(floor_number) and rings.get(floor_number, []).size() == 2, "L%d needs one disc and two central rings" % floor_number)
		for centre: Vector3 in rings.get(floor_number, []):
			var disc: Vector3 = discs.get(floor_number, Vector3.ZERO)
			check(Vector2(centre.x - disc.x, centre.z - disc.z).length() < 0.002, "L%d disc and rings must be coaxial in the actual world transform" % floor_number)
	check(facade_panes == 9, "Transmission regression must cover the real nine central facade panes")
	check(daybed_backs == 1 and front_fixture_parts == 3, "Placement regression must cover the actual front daybed and all three parts of its existing ceiling fixture")
	check(ceilings == 8 and coves == 8 and linings >= 64, "Lighting fix must cover all eight bedrooms and their bed linings")
	check(patterned_rugs == 1, "Review must cover the actual block-play rug")
	for floor_number in [2, 3]:
		check(outward_faces[floor_number] >= 4 and float(illuminated_faces[floor_number]) / outward_faces[floor_number] >= 0.85, "L%d existing ceiling fixtures must reach the outward-facing seating surfaces (%d/%d)" % [floor_number, illuminated_faces[floor_number], outward_faces[floor_number]])
	estate.free()
	for message in failures: push_error(message)
	if failures.is_empty(): print("PASS designed sources only, three concentric ceilings, eight bedrooms and original patchwork rug")
	quit(0 if failures.is_empty() else 1)

func check_interior_light_budget(estate: Node3D) -> void:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(627, 688)
	root.add_child(viewport)
	var camera := Camera3D.new()
	camera.fov = 58.0
	viewport.add_child(camera)
	var lights := estate.find_children("*", "SpotLight3D", true, false)
	var views: Array = []
	for floor_number in [1, 2, 3]:
		var centre := Vector3(0.0, 2.5 + (floor_number - 1) * 2.8, 0.0)
		for angle in range(0, 360, 45):
			var eye := centre + Vector3(sin(deg_to_rad(angle)) * 5.5, 0.5, cos(deg_to_rad(angle)) * 5.5)
			views.append([eye, centre, "L%d interior yaw %d" % [floor_number, angle]])
	views.append([Vector3(0,5.8,6.4), Vector3(0,1.2,26), "South window"])
	for view: Array in views:
		camera.global_position = view[0]
		camera.look_at(view[1])
		var planes := camera.get_frustum()
		var count := 0
		for light: SpotLight3D in lights:
			if not light.is_visible_in_tree(): continue
			if light.distance_fade_enabled and camera.global_position.distance_to(light.global_position) > light.distance_fade_begin + light.distance_fade_length: continue
			var bounds: AABB = light.global_transform * light.get_aabb()
			var clipped := false
			for plane: Plane in planes:
				var outside := true
				for corner in range(8):
					if not plane.is_point_over(bounds.get_endpoint(corner)):
						outside = false
						break
				if outside:
					clipped = true
					break
			if not clipped: count += 1
		check(count <= 16384 / 112, "%s has %d spots; outdoor lights must also fit the WebGL buffer when looking out" % [view[2], count])
	viewport.free()


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
		var label := str(extras.get("source_name", mesh.name))
		if not (label.begins_with("Central L4 round arrival floor") or label == "Central single continuous full-height envelope" or label.begins_with("Central L3 fitted reveal quadrant")): continue
		for surface in range(mesh.mesh.get_surface_count()):
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if indices.is_empty():
				indices.resize(points.size())
				for vertex in range(points.size()): indices[vertex] = vertex
			for i in range(0, indices.size(), 3):
				var hit: Variant = Geometry3D.ray_intersects_triangle(origin, up, mesh.global_transform * points[indices[i]], mesh.global_transform * points[indices[i + 1]], mesh.global_transform * points[indices[i + 2]])
				if hit != null and (hit as Vector3).distance_to(fixture.global_position) < 0.03: return true
	return false
