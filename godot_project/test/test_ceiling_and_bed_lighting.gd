extends SceneTree

const DAYLIGHT := preload("res://nest/rendering/estate_daylight.gd")
const SURFACE := preload("res://nest/rendering/estate_surface.gd")
const CONTROL := preload("res://nest/rendering/estate_lighting.gd")
var failures: Array[String] = []
var _texture_samples := {}
var _normal_pairs := {}
var fixture_sources: Dictionary = {}
var source_fixtures: Dictionary = {}

func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	index_fixture_sources(estate)
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
		if module == "central" and mesh.mesh != null:
			for surface in range(mesh.mesh.get_surface_count()):
				var original := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
				if original == null or not original.resource_name.to_lower().begins_with("trial nearly clear ice-aqua facade glass"): continue
				if label == "central l1 curved front glass" or label.begins_with("central l2 curved glass quadrant ") or label.begins_with("central l3 curved glass quadrant "):
					facade_panes += 1
				var pane := mesh.get_active_material(surface) as BaseMaterial3D
				# Split GLB already contains the calibrated per-face alpha.
				check(pane != null and pane.albedo_color.is_equal_approx(original.albedo_color), "Facade must retain calibrated split-GLB color and alpha without a second calibration")
				check_native_material(mesh, surface, original, pane)
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
				for light: Light3D in fixture_sources.get(mesh, []):
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
			var actual_lights: Array = (fixture_sources.get(mesh, []) as Array).filter(func(light: Node) -> bool: return light.get_meta("asset_role", "") == "authored-daylight-fixture")
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
			check((fixture_sources.get(mesh, []) as Array).filter(func(light: Light3D) -> bool: return str(light.name).begins_with("BedroomCoveDiffuse")).is_empty(), "%s must not gain perimeter fill lights" % module)
		if label == "games_front_play_rug":
			patterned_rugs += 1
			var material := mesh.get_active_material(0) as ShaderMaterial
			var pattern := material.get_shader_parameter("source_albedo_texture") as Texture2D if material != null else null
			var weave := material.get_shader_parameter("source_normal_texture") as Texture2D if material != null else null
			check(pattern != null and pattern.resource_path.ends_with("/central-play-rug-color.png")
				and bool(material.get_shader_parameter("use_albedo_texture"))
				and not bool(material.get_shader_parameter("use_linear_vertex_color")), "Play rug must render its baked patchwork colors")
			check(weave != null and weave.resource_path.ends_with("/central-play-rug-normal.png")
				and bool(material.get_shader_parameter("use_normal_texture")), "Play rug must retain its fine fabric normal")
		if module in DAYLIGHT.POD_MODULES and str(extras.get("piece", "")) in ["inner_wrap", "inner_welt"]:
			linings += 1
			for i in range(mesh.mesh.get_surface_count()):
				var original := mesh.mesh.surface_get_material(i) as BaseMaterial3D
				var actual := mesh.get_active_material(i) as ShaderMaterial
				check(actual != null and actual.shader == SURFACE.OPAQUE, "%s bed lining needs the physical room material path" % module)
				if actual != null:
					check(actual.get_shader_parameter("source_albedo") == original.albedo_color, "Bed lining must retain the authored sage color")
					check_bed_normal_variant(mesh, i, actual, original)
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
	views.append([Vector3(21,17,28), Vector3(0,3,7), "Exterior"])
	for view: Array in views:
		camera.global_position = view[0]
		camera.look_at(view[1])
		var planes := camera.get_frustum()
		var count := 0
		var sources: Array[String] = []
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
			if not clipped:
				count += 1
				sources.append(light_diagnostic(light))
		check(count <= 16384 / 112, "%s has %d spots (limit 146); sources=%s" % [view[2], count, sources])
	viewport.free()


func reaches_outward_face(estate: Node3D, receiver: MeshInstance3D, sample: Vector3, normal: Vector3) -> bool:
	var candidates: Array[String] = []
	for light: SpotLight3D in estate.find_children("*", "SpotLight3D", true, false):
		var fixture := source_fixtures.get(light) as MeshInstance3D
		if fixture == null: continue
		var extras: Dictionary = fixture.get_meta("extras", {})
		if not " downlight " in str(extras.get("source_name", fixture.name)).to_lower(): continue
		if (light.light_cull_mask & receiver.layers) == 0: continue
		var ray := sample - light.global_position
		if normal.dot(-ray.normalized()) > 0.0:
			candidates.append("%s position=%s facing=%.3f angle=%.1f limit=%.1f" % [light_diagnostic(light), light.global_position, normal.dot(-ray.normalized()), rad_to_deg(acos(clampf((-light.global_basis.z).dot(ray.normalized()), -1.0, 1.0))), light.spot_angle])
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


func placement_module(node: Node) -> String:
	var extras: Dictionary = node.get_meta("extras", {})
	if extras.has("module"): return str(extras.module)
	var ancestor := node.get_parent()
	while ancestor != null:
		if ancestor.has_meta("estate_module"): return str(ancestor.get_meta("estate_module"))
		ancestor = ancestor.get_parent()
	return ""


func index_fixture_sources(estate: Node3D) -> void:
	var fixtures := {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var path := str(mesh.get_meta("v044_path", ""))
		if path.is_empty(): continue
		var key := placement_module(mesh) + ":" + path
		if not fixtures.has(key): fixtures[key] = []
		fixtures[key].append(mesh)
	for light: Light3D in estate.find_children("*", "Light3D", true, false):
		var path := str(light.get_meta("v044_path", ""))
		if path.is_empty(): continue
		# Shared room GLBs retain M01 source paths; actual placement module
		# and floor metadata distinguish all eight rooms, never a basename.
		var matches: Array = fixtures.get(placement_module(light) + ":" + path.get_base_dir(), [])
		var extras: Dictionary = light.get_meta("extras", {})
		if extras.has("floor"):
			matches = matches.filter(func(mesh: MeshInstance3D) -> bool: return int((mesh.get_meta("extras", {}) as Dictionary).get("floor", 1)) == int(extras.floor))
		check(matches.size() <= 1, "Ambiguous fixture source: " + light_diagnostic(light))
		if matches.size() != 1: continue
		var fixture: MeshInstance3D = matches[0]
		source_fixtures[light] = fixture
		if not fixture_sources.has(fixture): fixture_sources[fixture] = []
		fixture_sources[fixture].append(light)


func light_diagnostic(light: Light3D) -> String:
	return "%s module=%s source=%s energy=%.3f mask=%d" % [light.get_path(), placement_module(light), light.get_meta("v044_path", ""), light.light_energy, light.light_cull_mask]


func check_bed_normal_variant(mesh: MeshInstance3D, surface: int, actual: ShaderMaterial, original: BaseMaterial3D) -> void:
	var context := "%s surface=%d" % [mesh.get_path(), surface]
	var variants: Variant = mesh.get_parent().get("material_variants")
	check(variants is Dictionary, "Bed lining needs declared SCN material variants: " + context)
	if not variants is Dictionary: return
	var surfaces: Array = variants.get(mesh.get_index(), [])
	check(surface < surfaces.size(), "Bed lining needs a declared SCN surface variant: " + context)
	if surface >= surfaces.size(): return
	var declared := surfaces[surface] as ShaderMaterial
	check(declared != null and declared.shader == SURFACE.OPAQUE, "Bed lining needs its declared physical SCN material: " + context)
	if declared == null: return
	var reference := declared.get_shader_parameter("source_normal_texture") as Texture2D
	var effective := actual.get_shader_parameter("source_normal_texture") as Texture2D
	check(reference != null and effective != null, "Bed normal texture binding missing: " + context)
	check(same_texture(effective, reference), "Bed normal must strictly retain all RGBA pixels of the declared SCN variant: " + context)
	check(bool(declared.get_shader_parameter("use_normal_texture")) and bool(actual.get_shader_parameter("use_normal_texture")), "Bed lining normal texture must be enabled: " + context)
	for parameter: String in ["use_normal_texture", "source_normal_scale", "source_uv_scale", "source_uv_offset"]:
		var expected: Variant = declared.get_shader_parameter(parameter)
		check(expected != null and actual.get_shader_parameter(parameter) == expected, "Bed lining must retain declared SCN %s: %s" % [parameter, context])
	check(original != null, "Bed lining needs the GLB prototype material: " + context)
	if original != null:
		check(normal_matches_glb(reference, original.normal_texture), "Declared SCN normal must retain GLB R/G/A with only the measured RGB8-to-RGBA8 B conversion: " + context)


func normal_matches_glb(reference: Texture2D, prototype: Texture2D) -> bool:
	var a := texture_pixels(reference)
	var b := texture_pixels(prototype)
	if not a.has("pixels") or not b.has("pixels") or a["size"] != b["size"]: return false
	var pair := str(a.sha256) + ":" + str(b.sha256)
	if _normal_pairs.has(pair): return _normal_pairs[pair]
	var native: PackedByteArray = a.pixels
	var glb: PackedByteArray = b.pixels
	if native == glb:
		_normal_pairs[pair] = true
		return true
	# This exact accepted native/export pair differs only in the encoded Z
	# channel. The effective shader is checked against all RGBA native pixels
	# above. Record the complete pair, not a guessed per-pixel tolerance.
	var known: bool = a.sha256 == "e706d172c0b6459002b3f2bbd127f8988172184089c0af931c6162bb0f7f066c" and b.sha256 == "0a123e925952c7a00e7be50542fca32e7bbc55ed6878724b92c7be317ccf1d9a"
	var matches: bool = known and native.size() == glb.size()
	if matches:
		for offset: int in range(0, native.size(), 4):
			if native[offset] != glb[offset] or native[offset+1] != glb[offset+1] or native[offset+3] != glb[offset+3]:
				matches = false
				break
	_normal_pairs[pair] = matches
	if not matches: print("BED_NORMAL_UNEXPECTED_EXPORT ", JSON.stringify(normal_pixel_difference(a,b)))
	return matches


func same_texture(actual: Texture2D, original: Texture2D) -> bool:
	var actual_info := texture_pixels(actual)
	var original_info := texture_pixels(original)
	var equal := false
	if actual == null or original == null:
		equal = false # A missing normal binding must never pass, even if both are null.
	elif actual_info.has("pixels") and original_info.has("pixels"):
		equal = actual_info["size"] == original_info["size"] and actual_info["pixels"] == original_info["pixels"]
	if not equal:
		print("BED_NORMAL_PIXEL_DIFF ", JSON.stringify(normal_pixel_difference(actual_info, original_info)))
		actual_info.erase("pixels")
		original_info.erase("pixels")
		print("BED_NORMAL_MISMATCH actual=", JSON.stringify(actual_info), " original=", JSON.stringify(original_info))
	return equal


func texture_pixels(texture: Texture2D) -> Dictionary:
	if texture == null: return {"texture_null": true}
	var identity := texture.get_instance_id()
	if _texture_samples.has(identity): return _texture_samples[identity].duplicate()
	var info := {"texture_null": false, "path": texture.resource_path, "class": texture.get_class(), "texture_size": str(texture.get_size())}
	var image := texture.get_image()
	info["image_null"] = image == null
	if image == null: return info
	# Work on a copy so inspection cannot mutate a resource's source image.
	image = image.duplicate() as Image
	info["source_format"] = image.get_format()
	info["source_compressed"] = image.is_compressed()
	info["source_mipmaps"] = image.has_mipmaps()
	if image.is_compressed():
		var error := image.decompress()
		info["decompress_error"] = error
		if error != OK: return info
	image.convert(Image.FORMAT_RGBA8)
	var pixels := image.get_data()
	var digest := HashingContext.new()
	digest.start(HashingContext.HASH_SHA256)
	digest.update(pixels)
	info["sha256"] = digest.finish().hex_encode()
	info["size"] = str(image.get_size())
	info["base_pixels"] = image.get_width() * image.get_height()
	info["format"] = image.get_format()
	info["mipmaps"] = image.has_mipmaps()
	info["bytes"] = pixels.size()
	info["pixels"] = pixels
	_texture_samples[identity] = info.duplicate()
	return info


func normal_pixel_difference(actual: Dictionary, original: Dictionary) -> Dictionary:
	if bool(actual.get("texture_null", false)) or bool(original.get("texture_null", false)):
		return {"status": "missing_texture_binding", "actual_null": actual.get("texture_null", false), "original_null": original.get("texture_null", false)}
	if not actual.has("pixels") or not original.has("pixels"):
		return {"status": "image_unavailable_or_decompression_failed"}
	if actual["size"] != original["size"]:
		return {"status": "different_dimensions", "actual_size": actual["size"], "original_size": original["size"]}
	var a: PackedByteArray = actual["pixels"]
	var b: PackedByteArray = original["pixels"]
	var result := {"units": "RGBA8 byte difference (0..255)", "base_level": rgba_pixel_difference(a, b, int(actual["base_pixels"]))}
	if a.size() == b.size():
		result["all_stored_levels"] = rgba_pixel_difference(a, b, a.size() / 4)
	else:
		result["stored_level_status"] = "different_byte_counts_or_mip_chains"
		result["actual_bytes"] = a.size()
		result["original_bytes"] = b.size()
	return result


func rgba_pixel_difference(a: PackedByteArray, b: PackedByteArray, pixel_count: int) -> Dictionary:
	if a.size() < pixel_count * 4 or b.size() < pixel_count * 4:
		return {"status": "insufficient_pixel_data", "requested_pixels": pixel_count}
	var maximum := [0, 0, 0, 0]
	var differing := [0, 0, 0, 0]
	var unequal_pixels := 0
	for pixel: int in pixel_count:
		var unequal := false
		for channel: int in 4:
			var delta := absi(int(a[pixel * 4 + channel]) - int(b[pixel * 4 + channel]))
			maximum[channel] = maxi(maximum[channel], delta)
			if delta != 0:
				differing[channel] += 1
				unequal = true
		if unequal: unequal_pixels += 1
	return {"channel_order": "RGBA", "pixels_compared": pixel_count, "max_absolute_difference": maximum, "unequal_pixels_per_channel": differing, "unequal_pixels": unequal_pixels, "rg_exact_b_differs": differing[0] == 0 and differing[1] == 0 and differing[2] > 0}


func check_native_material(mesh: MeshInstance3D, surface: int, original: BaseMaterial3D, actual: BaseMaterial3D) -> void:
	var extras: Dictionary = mesh.mesh.get_meta("nest_source_extras", {})
	var materials: Array = extras.get("nest_materials", [])
	if actual == null: return
	check(actual.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA and actual.depth_draw_mode == BaseMaterial3D.DEPTH_DRAW_DISABLED and not actual.refraction_enabled, "Facade effective SCN material must preserve thin alpha glazing without depth blocking")
	check(is_equal_approx(actual.roughness, original.roughness) and is_equal_approx(actual.metallic, original.metallic), "Facade must retain calibrated GLB roughness and metallic inputs")
	var ior := 1.46
	var specular := sqrt(pow((ior - 1.0) / (ior + 1.0), 2.0) / 0.16) * sqrt(1.25)
	check(is_equal_approx(actual.metallic_specular, specular), "Facade must retain native IOR and authored reflection-intensity calibration")
	# Some GLBs carry additional native-only settings; check each when present.
	if materials.is_empty(): return
	check(materials.size() == mesh.mesh.get_surface_count(), "Facade native material parameter count must match GLB surfaces")
	if surface >= materials.size(): return
	var values: Dictionary = materials[surface]
	for property: String in values:
		var expected: Variant = values[property]
		if property in ["emission", "albedo_color"]:
			expected = Color(expected[0], expected[1], expected[2], expected[3])
		check(is_same_material_value(original.get(property), expected), "GLB native material parameter differs: " + property)
		check(is_same_material_value(actual.get(property), expected), "Effective SCN native material parameter differs: " + property)


func is_same_material_value(actual: Variant, expected: Variant) -> bool:
	if actual is Color and expected is Color: return actual.is_equal_approx(expected)
	if actual is float or expected is float: return is_equal_approx(float(actual), float(expected))
	return actual == expected
