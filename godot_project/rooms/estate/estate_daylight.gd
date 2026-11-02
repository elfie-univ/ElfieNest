extends RefCounted
## Rendering-only daylight calibration; the imported asset stays untouched.

const SURFACE := preload("res://rooms/estate/estate_surface.gd")

# Restore the accepted daytime rig and its original shadowed-pass calibration.
const SHADOWED_PASS_SCALE := 0.04
const SUN_ENERGY := 1.05 / PI * SHADOWED_PASS_SCALE
const SUN_COLOR := Color(1.0, 231.0 / 255.0, 195.0 / 255.0, 1.0)
const INTERIOR_FILL_LAYER := 2
const OUTDOOR_LIGHT_LAYER := 4
const LANDSCAPE_LIGHT_LAYER := 16
const WATER_LIGHT_LAYER := 1 << 18
const OUTDOOR_SUN_ENERGY := SUN_ENERGY
const OBSERVATION_GLASS_ALPHA := 0.075
const FURNITURE_CONTACT_LAYER := 8
const NATIVE_HEMISPHERE_LAYER := 1 << 17
# Keep local fixture isolation separate from restored daytime hemisphere receivers.
const BOLLARD_FIXTURE_LAYER := 1 << 15
# Separate general room lighting from tiny stair/shelf accents in Compatibility.
const ACTIVITY_LAYERS := [INTERIOR_FILL_LAYER, 1 << 16, 1 << 19, 1 << 28]
const ROOF_ROOM_LAYER := 1 << 29
const NIGHT_NATURAL_SCALE := 0.0
const NIGHT_EMISSION := &"estate_night_emission_energy"
# The reference's day mode runs authored fixtures at 8%. Compatibility's
# non-physical Light3D energy is multiplied by PI before the same inverse-square
# light attenuation; convert that convention rather than copying raw intensity.
const DAYTIME_FIXTURE_SCALE := 0.08 / PI
# Broad ceiling fixtures overlap; retain surface detail in the LDR renderer.
const GENERAL_FIXTURE_BOOST := 3.125
# The opal fixture's authored point source provides its broad diffuse output.
const OPAL_DIFFUSER_BOOST := 37.5
const CEILING_WARM_WHITE := Color(1.0, 0.855, 0.69)
const POD_MODULES := ["M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08"]
# Distinguish authored bounce from powered fixture surfaces in diagnostics.
# Painted bounce is not an emitter. Only actual fixtures retain emission.
const AUTHORED_BOUNCE_NAMES := [
	"baked warm wash", "warm plaster returns", "continuous warm ivory plaster",
	"directly painted botanical sprig", "warm perimeter returns",
	"ceiling bounce", "ceiling warm bounce", "window reveal luminous return",
]
const ARTIFICIAL_EMISSION_NAMES := [
	"lighting", "light channel", "concealed", "lamp", "diffuser",
	"warm wash", "warm perimeter", "warm plaster returns", "warm bounce",
	"ceiling bounce", "ceiling warm bounce", "luminous", "downwash",
	"diffuse task wash", "double cove ivory shield", "doorway light",
	"continuous warm ivory plaster", "directly painted botanical sprig",
	"window reveal luminous return", "guide light",
]


static func apply(estate: Node) -> Dictionary:
	preload("res://rooms/estate/estate_stair_finish.gd").apply(estate as Node3D)
	_position_front_ceiling_fixture(estate)
	var materials: Dictionary = {}
	var windows: Dictionary = {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		SURFACE.repair_window_normals(mesh, windows)
		if (mesh.get_meta("extras", {}) as Dictionary).get("piece") == "bed_cover":
			mesh.mesh = SURFACE.duvet_rest(mesh.mesh)
	preload("res://rooms/estate/estate_bedding_layers.gd").attach(estate)
	var counts := {"sun": 0, "artificial_surfaces": 0, "sky_meshes": 0, "glass_surfaces": 0, "corrected_surfaces": 0}
	_calibrate(estate, materials, counts)
	# One physical sun illuminates every receiver once. Shared floor/ceiling
	# meshes carry multiple room masks; separate solar copies double-lit L2.
	for light: DirectionalLight3D in estate.find_children("*", "DirectionalLight3D", true, false):
		light.global_position = (estate as Node3D).to_global(Vector3(-20, 35, 24))
		light.look_at((estate as Node3D).global_position)
	for entry: Array in [[0xcdeaffff, 0.65, Vector3(22, 25, -24)], [0xffffffff, 0.30, Vector3(0, 15, 32)]]:
		var fill := DirectionalLight3D.new()
		fill.name = "CourtyardReferenceFillCool" if int(entry[0]) == 0xcdeaffff else "CourtyardReferenceFillFront"
		fill.light_cull_mask = INTERIOR_FILL_LAYER | OUTDOOR_LIGHT_LAYER | LANDSCAPE_LIGHT_LAYER | WATER_LIGHT_LAYER | BOLLARD_FIXTURE_LAYER
		fill.light_color = Color.hex(entry[0])
		fill.light_energy = float(entry[1]) / PI
		fill.set_meta("reference_intensity", entry[1])
		estate.add_child(fill)
		fill.global_position = (estate as Node3D).to_global(entry[2])
		fill.look_at((estate as Node3D).global_position)
	var contact_rooms: Dictionary = {}
	# Textured native materials need the same normal-dependent hemisphere as
	# custom surfaces. Do not add it twice to shaders that own IRRADIANCE.
	var upper := Color.hex(0xd7ebffff).srgb_to_linear()
	var lower := Color.hex(0x5a685dff).srgb_to_linear()
	for up in [true, false]:
		var hemisphere := DirectionalLight3D.new()
		hemisphere.name = "NativeHemisphereUpper" if up else "NativeHemisphereLower"
		hemisphere.light_color = ((upper - lower) * 0.5).linear_to_srgb()
		hemisphere.light_energy = 0.72 / PI
		hemisphere.light_negative = not up
		hemisphere.light_specular = 0.0
		hemisphere.light_cull_mask = NATIVE_HEMISPHERE_LAYER
		hemisphere.rotation_degrees.x = -90.0 if up else 90.0
		estate.add_child(hemisphere)
	var ceiling_targets: Dictionary = {}
	for fixture: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = fixture.get_meta("extras", {})
		if extras.get("module") != "central" or "circular opal ceiling diffuser" not in str(extras.get("source_name", fixture.name)).to_lower(): continue
		for source: Dictionary in extras.get("design_lights", []):
			if source.get("type") != "spot" or float(source.get("angle", 0.0)) < 1.0: continue
			var centre := (fixture.global_transform * fixture.get_aabb()).get_center()
			centre.y = (fixture.global_transform * _vector(source["target"])).y + 0.9
			ceiling_targets[int(extras.get("floor", 1))] = centre
			break
	for mesh: Node in estate.find_children("*", "MeshInstance3D", true, false):
		_restore_fixture_lights(mesh as MeshInstance3D, contact_rooms, ceiling_targets)
		var extras: Dictionary = mesh.get_meta("extras", {})
		if extras.get("lighting_kind")=="stair" and extras.get("stair_edge_role")=="side" and not (extras.get("design_lights",[]) as Array).is_empty():
			# Concealed strips provide indirect light through their real sources.
			# Keep the owner visible for those child lights, but do not render
			# the old exposed contour surface outside its shielding lip.
			(mesh as MeshInstance3D).layers=0
			(mesh as MeshInstance3D).cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# Existing opal bedroom fixtures carry their own actual light source.
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		var label := str(extras.get("source_name", mesh.name))
		if "five-petal solid opal ceiling lamp" not in label: continue
		var lamp := OmniLight3D.new()
		lamp.name = "BedroomCeiling" + str(extras.get("module", ""))
		lamp.light_color = Color.hex(0xffdfb5ff)
		lamp.light_energy = 6.0 / PI
		lamp.omni_range = 8.0
		lamp.omni_attenuation = 2.0
		lamp.light_cull_mask = _room_light_mask(extras)
		lamp.top_level = true
		lamp.set_meta("asset_role", "authored-daylight-fixture")
		lamp.set_meta("estate_fixture_calibrated", true)
		lamp.set_meta("estate_initial_light_visible", true)
		mesh.add_child(lamp)
		var bounds := mesh.global_transform * mesh.get_aabb()
		lamp.global_position = bounds.get_center()
		lamp.global_position.y = bounds.position.y - 0.03
		if str(extras.get("module", "")) in POD_MODULES:
			lamp.light_color = CEILING_WARM_WHITE
			lamp.light_energy = 8.0 / PI
			lamp.omni_range = 10.0
			lamp.omni_attenuation = 1.0
			lamp.light_specular = 0.0
		lamp.visible = false
	if OS.has_feature("web"):
		for sun: DirectionalLight3D in estate.find_children("*", "DirectionalLight3D", true, false):
			if sun.shadow_enabled:
				_apply_web_shadow_budget(sun)
	return counts


static func _position_front_ceiling_fixture(estate: Node) -> void:
	var roof: MeshInstance3D
	var daybed: MeshInstance3D
	var parts: Array[MeshInstance3D] = []
	var supports: Array[MeshInstance3D] = []
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		var label := str(extras.get("source_name", mesh.name))
		if label.begins_with("Central L4 round arrival floor"): roof = mesh
		if label == "quiet_front_sage_daybed": daybed = mesh
		if label.begins_with("Working L3 downlight 1 "): parts.append(mesh)
		if label.begins_with("Central L4 round arrival floor") or label == "Central single continuous full-height envelope" or label.begins_with("Central L3 fitted reveal quadrant"):
			supports.append(mesh)
	if roof == null or daybed == null or parts.is_empty(): return
	var bed_bounds := daybed.global_transform * daybed.get_aabb()
	var roof_bounds := roof.global_transform * roof.get_aabb()
	# The existing front lamp must be on the window side of the backrest.
	# Its body, rim and baffle stay together on the real curved underside.
	var origin := Vector3(bed_bounds.get_center().x, roof_bounds.end.y + 1.0, minf(bed_bounds.end.z + 1.55, roof_bounds.end.z + 0.05))
	var mounting := Vector3(0.0, INF, 0.0)
	var normal := Vector3.UP
	for support: MeshInstance3D in supports:
		for surface in range(support.mesh.get_surface_count()):
			var arrays := support.mesh.surface_get_arrays(surface)
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if indices.is_empty():
				indices.resize(points.size())
				for vertex in range(points.size()): indices[vertex] = vertex
			for i in range(0, indices.size(), 3):
				var a := support.global_transform * points[indices[i]]
				var b := support.global_transform * points[indices[i + 1]]
				var c := support.global_transform * points[indices[i + 2]]
				var hit: Variant = Geometry3D.ray_intersects_triangle(origin, Vector3.DOWN, a, b, c)
				if hit == null or (hit as Vector3).y >= mounting.y or (hit as Vector3).y < roof_bounds.position.y: continue
				mounting = hit
				normal = (b - a).cross(c - a).normalized()
				if normal.y < 0.0: normal = -normal
	if not is_finite(mounting.y):
		push_error("Front ceiling fixture could not be mounted on the actual roof")
		return
	var right := normal.cross(Vector3.BACK).normalized()
	var basis := Basis(right, normal, right.cross(normal).normalized())
	var target := Vector3(bed_bounds.get_center().x, bed_bounds.position.y + bed_bounds.size.y * 0.55, bed_bounds.end.z)
	for part: MeshInstance3D in parts:
		part.global_transform = Transform3D(basis, mounting + normal * 0.001)
		part.set_meta("estate_ceiling_target", target)


static func _apply_web_shadow_budget(sun: DirectionalLight3D) -> void:
	# Preserve near shadows; fade distant shadow work rather than scenery.
	sun.directional_shadow_max_distance = minf(sun.directional_shadow_max_distance, 30.0)
	sun.directional_shadow_fade_start = minf(sun.directional_shadow_fade_start, 0.7)
	sun.directional_shadow_mode = mini(sun.directional_shadow_mode, DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS) as DirectionalLight3D.ShadowMode


static func _calibrate(node: Node, materials: Dictionary, counts: Dictionary) -> void:
	if node is DirectionalLight3D:
		var sunlight := node as DirectionalLight3D
		sunlight.light_color = SUN_COLOR
		sunlight.light_energy = SUN_ENERGY
		sunlight.shadow_enabled = true
		sunlight.light_cull_mask = 0xFFFFF
		counts["sun"] += 1
	elif node is Light3D:
		(node as Light3D).visible = false
	if node is MeshInstance3D:
		var instance := node as MeshInstance3D
		var extras := instance.get_meta("extras", {}) as Dictionary
		instance.layers |= _room_light_mask(extras)
		var bedroom_ceiling := str(extras.get("module", "")) in POD_MODULES and str(extras.get("source_name", instance.name)).begins_with("ROOM • structural terrace slab")
		# The terrace slab also owns the bedroom's ceiling underside. Its
		# downward-facing ivory surface needs the lower room's actual lights.
		if bedroom_ceiling:
			instance.layers |= _room_light_mask({"module": extras["module"], "floor": 1})
		var source_name := str(extras.get("source_name", instance.name)).to_lower()
		var room_receiver := str(extras.get("module", "")) == "central" and (bool(extras.get("furniture", false)) or "floor" in source_name or "slab" in source_name)
		var room_group := "central-%02d" % clampi(int(extras.get("floor", 1)), 1, 4) if room_receiver else ""
		if room_receiver:
			# The floor and furniture reliably receive the existing general ceiling
			# fixtures, instead of spending their eight-light budget on stair LEDs.
			instance.layers &= ~_room_light_mask(extras)
			instance.layers |= _activity_light_mask(extras)
		elif _is_central_interior_surface(instance):
			# Ceiling diffusers also illuminate interior plaster and walls, while
			# glazing and exterior shells retain their separate lighting layers.
			instance.layers |= _activity_light_mask(extras)
		if bool(extras.get("furniture", false)):
			instance.layers |= FURNITURE_CONTACT_LAYER
		# Module membership includes the facade as well as the room. Do not
		# expose exterior shells and glazing to the accepted interior fill.
		instance.layers &= ~(INTERIOR_FILL_LAYER | OUTDOOR_LIGHT_LAYER)
		if _uses_interior_fill(instance):
			instance.layers |= INTERIOR_FILL_LAYER
		else:
			instance.layers |= OUTDOOR_LIGHT_LAYER
		if str(extras.get("outdoor_fixture_id", "")) in ["B01","B02"]:
			# One point source represents the luminous ring. Keep its closed
			# casing/diffuser out of its own shadow map, retaining their shadows
			# from the sun and every other type of fixture.
			instance.layers = BOLLARD_FIXTURE_LAYER
		# Shared slabs own the ceiling below as well as the floor above.
		# Restore the lower mask after normalizing indoor/outdoor layers.
		var ceiling_floor := int(extras.get("ceiling_for_floor", 0))
		if str(extras.get("module", "")) == "central" and ceiling_floor in [1, 2, 3]:
			instance.layers |= _activity_light_mask({"floor": ceiling_floor})
		if instance.mesh != null:
			for surface in range(instance.mesh.get_surface_count()):
				var original := instance.get_active_material(surface) as BaseMaterial3D
				if original == null:
					continue
				var material_name := original.resource_name.to_lower()
				if original.emission_enabled and _is_authored_bounce(material_name):
					original = original.duplicate() as BaseMaterial3D
					original.emission_enabled = false
					instance.set_surface_override_material(surface, original)
				if _is_background(material_name):
					# The existing sky is geometry, not an Environment sky. It must
					# neither change color nor occlude the real sun when shadows work.
					instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
					counts["sky_meshes"] += 1
					continue
				var observation_glass := _is_observation_glass(material_name)
				var facade_glass := material_name == "trial nearly clear ice-aqua facade glass"
				var optics: Dictionary = original.get_meta("source_optics", {})
				var transmission := float(optics.get("transmission", 0.0))
				var clear_glazing := observation_glass or facade_glass or transmission > 0.0
				if bool(extras.get("roof_skylight", false)) and transmission > 0.0:
					var glass_key := "glass:%d" % original.get_instance_id()
					if not materials.has(glass_key):
						materials[glass_key] = SURFACE.make_glass(original, optics)
					instance.set_surface_override_material(surface, materials[glass_key])
					instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
					counts["glass_surfaces"] += 1
					continue
				var finish := (original.get_meta("extras", {}) as Dictionary).get("preview_surface_finish", {}) as Dictionary
				var diffuser := original.emission_enabled and bool(extras.get("lighting_diffuser", false)) and not (extras.get("design_lights", []) as Array).is_empty()
				var artificial := original.emission_enabled and _is_artificial(material_name)
				var roof_emitter := str(extras.get("module", "")) == "central" and int(extras.get("floor", 1)) == 4 and material_name.begins_with("roof") and artificial
				var vertex_painted := instance.mesh is ArrayMesh and bool(instance.mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR)
				var bed_lining := str(extras.get("module", "")) in POD_MODULES and str(extras.get("piece", "")) in ["inner_wrap", "inner_welt"]
				var physical_surface := SURFACE.supports(original, true, room_receiver or bed_lining or bedroom_ceiling) and not _is_landscape_template(instance)
				# glTF COLOR_0 is authored albedo, including the play rug's
				# patchwork. The imported shared material may leave it disabled.
				var uses_vertex_color := vertex_painted
				var sheen: Dictionary = optics.get("sheen", {})
				var fabric_surface := not sheen.is_empty() and original.albedo_texture == null and not original.emission_enabled and not vertex_painted and not _is_landscape_template(instance)
				if not clear_glazing and not artificial and finish.is_empty() and not diffuser and not physical_surface and not fabric_surface:
					continue
				# A shared material can belong to both a powered diffuser and an
				# unpowered decorative ring; their day intensities differ.
				var identity := "%d:%s:%s:%s:%s" % [original.get_instance_id(), diffuser, uses_vertex_color, room_group, roof_emitter]
				if not materials.has(identity):
					var calibrated := original.duplicate() as BaseMaterial3D
					calibrated.vertex_color_use_as_albedo = uses_vertex_color
					if diffuser:
						calibrated.emission_enabled = true
						calibrated.emission_energy_multiplier = 1.0 if extras.has("outdoor_fixture_id") else 0.15
						calibrated.set_meta(NIGHT_EMISSION, 1.0)
					if roof_emitter:
						# Keep the imported cyan/radial textures and day inputs. Their
						# original 1.6–3.6 emission clips to white in the LDR night view.
						calibrated.set_meta(NIGHT_EMISSION, minf(original.emission_energy_multiplier, 0.35 if original.emission_texture != null else 0.65))
					if clear_glazing:
						# This source uses glTF transmission=1 with alpha=1. The
						# Compatibility importer leaves it opaque. Use thin tinted
						# alpha glazing, retaining its RGB, roughness and geometry.
						calibrated.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
						calibrated.refraction_enabled = false
						if observation_glass:
							calibrated.albedo_color.a = OBSERVATION_GLASS_ALPHA
						elif transmission > 0.0:
							calibrated.albedo_color.a = 1.0 - transmission
						elif facade_glass:
							# These closed panes have two rendered faces. Preserve
							# the authored whole-pane opacity across both faces,
							# rather than applying the full absorption twice.
							calibrated.albedo_color.a = 1.0 - sqrt(1.0 - original.albedo_color.a)
						# Compatibility specular is sqrt(F0 / .16). Authored IOR is
						# 1.12 for pod panes and 1.46 for central facade glass.
						calibrated.metallic_specular = _glass_specular(1.12 if observation_glass else 1.46)
						calibrated.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
					if not finish.is_empty():
						# glTF's clearcoat/IOR extensions are not imported into the
						# native material. Restore their actual source values, not a
						# recolor or a generic gloss/roughness replacement.
						calibrated.metallic_specular = _glass_specular(float(optics["ior"])) * sqrt(float(finish["reflectionIntensity"]))
						calibrated.clearcoat_enabled = true
						calibrated.clearcoat = float(optics["clearcoat"])
						calibrated.clearcoat_roughness = float(optics["clearcoat_roughness"])
					if fabric_surface:
						materials[identity] = SURFACE.make_sheen(original, sheen)
					elif not clear_glazing and physical_surface:
						materials[identity] = SURFACE.make_material(calibrated, float(optics.get("clearcoat", 0.0)), float(optics.get("clearcoat_roughness", 0.0)), uses_vertex_color)
					else:
						materials[identity] = calibrated
				instance.set_surface_override_material(surface, materials[identity])
				if materials[identity] is ShaderMaterial:
					if room_receiver and not clear_glazing:
						(materials[identity] as ShaderMaterial).set_meta("estate_room_group", room_group)
					counts["corrected_surfaces"] += 1
				if clear_glazing:
					instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
					counts["glass_surfaces"] += 1
				if artificial:
					counts["artificial_surfaces"] += 1

			var needs_hemisphere := false
			var owns_irradiance := false
			for surface in range(instance.mesh.get_surface_count()):
				var actual := instance.get_active_material(surface)
				owns_irradiance = owns_irradiance or actual is ShaderMaterial
				var native := actual as BaseMaterial3D
				if native != null and native.albedo_texture != null and native.shading_mode == BaseMaterial3D.SHADING_MODE_PER_PIXEL and not bool(extras.get("glass", false)):
					needs_hemisphere = true
			# Light layers are per instance, not per surface: mixed meshes must
			# not add native hemisphere lights to custom IRRADIANCE a second time.
			if needs_hemisphere and not owns_irradiance:
				instance.layers |= NATIVE_HEMISPHERE_LAYER
	for child: Node in node.get_children():
		_calibrate(child, materials, counts)


static func _is_central_interior_surface(instance: MeshInstance3D) -> bool:
	var extras := instance.get_meta("extras", {}) as Dictionary
	if str(extras.get("module", "")) != "central" or int(extras.get("floor", 1)) not in [1, 2, 3, 4] or bool(extras.get("glass", false)) or bool(extras.get("full_height", false)):
		return false
	if instance.mesh == null: return false
	for surface in range(instance.mesh.get_surface_count()):
		var material := instance.get_active_material(surface)
		if material == null: continue
		var label := material.resource_name.to_lower()
		if label.begins_with("exterior •") or "facade" in label or "window reveal" in label or "window and door surrounds" in label:
			return false
	return true


static func _uses_interior_fill(instance: MeshInstance3D) -> bool:
	var extras := instance.get_meta("extras", {}) as Dictionary
	# Only the already-reviewed ground-floor common room retains this fill.
	# Pods and upper/roof rooms use soft daylight rather than the same bright
	# indoor rig, including the furniture seen through their observation glass.
	if (
		str(extras.get("module", "")) != "central"
		or int(extras.get("floor", 1)) != 1
		or bool(extras.get("glass", false))
	):
		return false
	if bool(extras.get("furniture", false)):
		return true
	if instance.mesh != null:
		for surface in range(instance.mesh.get_surface_count()):
			var material := instance.get_active_material(surface)
			if material == null:
				continue
			var material_name := material.resource_name.to_lower()
			if (
				material_name.begins_with("exterior •")
				or "facade" in material_name
				or "window reveal" in material_name
				or "window and door surrounds" in material_name
			):
				return false
	return true


static func _activity_light_mask(extras: Dictionary) -> int:
	return ACTIVITY_LAYERS[clampi(int(extras.get("floor", 1)), 1, 4) - 1]


static func _is_landscape_template(instance: Node) -> bool:
	# Sidecar restoration owns these prototypes, including vertex color setup
	# and the approved full-detail canopy classification.
	var ancestor := instance
	while ancestor != null:
		if str(ancestor.name).begins_with("__ELFIE_INST_GROUP_"):
			return true
		ancestor = ancestor.get_parent()
	return false


static func _room_light_mask(extras: Dictionary) -> int:
	if extras.has("outdoor_fixture_id"):
		return OUTDOOR_LIGHT_LAYER | LANDSCAPE_LIGHT_LAYER
	var module := str(extras.get("module", ""))
	if module == "central":
		if bool(extras.get("full_height", false)):
			return (1 << 5) | (1 << 6) | (1 << 7) | ROOF_ROOM_LAYER
		if int(extras.get("floor", 1)) == 4: return ROOF_ROOM_LAYER
		return 1 << (4 + clampi(int(extras.get("floor", 1)), 1, 3))
	if module in POD_MODULES:
		if int(extras.get("floor", 1)) == 2:
			return 1 << (19 + int(module.trim_prefix("M")))
		return 1 << (7 + int(module.trim_prefix("M")))
	return 0


static func _is_observation_glass(material_name: String) -> bool:
	return material_name.begins_with("06 • clear observation glass")


static func _is_background(material_name: String) -> bool:
	return (
		material_name.begins_with("approved static sky ")
		or material_name == "approved blue sky white clouds dome inner side"
		or material_name == "approved misty forest wall with sky transition"
	)


static func _is_artificial(material_name: String) -> bool:
	if _is_authored_bounce(material_name):
		return false
	for token: String in ARTIFICIAL_EMISSION_NAMES:
		if token in material_name:
			return true
	return false


static func _is_authored_bounce(material_name: String) -> bool:
	for token: String in AUTHORED_BOUNCE_NAMES:
		if token in material_name:
			return true
	return false


static func _glass_specular(ior: float) -> float:
	return SURFACE.specular_from_ior(ior)


static func _restore_fixture_lights(mesh: MeshInstance3D, contact_rooms: Dictionary, ceiling_targets: Dictionary) -> void:
	var extras := mesh.get_meta("extras", {}) as Dictionary
	var room := "%s:%s" % [extras.get("module", ""), extras.get("floor", 1)]
	var label := str(extras.get("source_name", mesh.name)).to_lower()
	var central := str(extras.get("module", "")) == "central"
	var pod_terrace := str(extras.get("module", "")) in POD_MODULES and label == "terrace • inner parapet concealed warm strip"
	var opal := central and "circular opal ceiling diffuser" in label
	var downlight := central and " downlight " in label
	var perimeter_downlight := downlight and ("distributed ceiling downlight" in label or int(extras.get("floor", 1)) == 3)
	for source: Dictionary in extras.get("design_lights", []):
		var spot := str(source["type"]) == "spot"
		var light: Light3D = SpotLight3D.new() if spot else OmniLight3D.new()
		light.name = "AuthoredDaylightFixture"
		# Source positions/targets are in the owning fixture's local frame.
		# Bake that frame once, so mesh non-uniform scale cannot distort range.
		light.top_level = true
		light.light_color = Color.hex((int(source.get("color", 0xffdfb5)) << 8) | 0xff)
		var outdoor := extras.has("outdoor_fixture_id")
		light.light_energy = float(source["intensity"]) * (1.0 / PI if outdoor else DAYTIME_FIXTURE_SCALE)
		if pod_terrace:
			light.light_color = CEILING_WARM_WHITE
			light.light_energy = 2.4 * DAYTIME_FIXTURE_SCALE
			light.light_specular = 0.0
		light.light_cull_mask = _room_light_mask(extras)
		if outdoor:
			light.light_cull_mask |= BOLLARD_FIXTURE_LAYER
		if outdoor and str(extras.get("outdoor_fixture_id", "")) in ["H01","B01","B02"]:
			# Keep the accepted lakeside occlusion local. Other fixtures retain
			# their original rendering instead of inheriting global shadows.
			light.shadow_enabled = true
			light.shadow_caster_mask = 0xFFFFF
			if str(extras.get("outdoor_fixture_id", "")) in ["B01","B02"]:
				light.shadow_caster_mask &= ~BOLLARD_FIXTURE_LAYER
			light.shadow_bias = 0.1
			light.shadow_normal_bias = 3.0
		var general := opal or downlight
		if central and spot and not general:
			# Short-range task/edge lights fade beyond their local room.
			# WebGL's 16 KiB light buffer holds 146 spots; these 42 local
			# accents otherwise displace real ceiling beams from that buffer.
			# Their emissive fixtures and all ceiling lights remain visible.
			light.distance_fade_enabled = true
			light.distance_fade_begin = 8.0
			light.distance_fade_length = 2.0
		if general:
			light.light_color = CEILING_WARM_WHITE
		if opal:
			# The broad opal face is represented by diffuse sources, not tiny
			# mirror-bright points on the floor. Keep narrow task accents intact.
			if not spot or float(source.get("angle", 0.0)) > 1.0:
				light.light_specular = 0.0
				var floor_number := int(extras.get("floor", 1))
				# Four central beams overlap on the same seating. Budget their
				# combined output, with the accepted bedroom lamp as a reference.
				var intensity := (14.0 if floor_number == 1 else 6.0) if spot else (2.6 if floor_number == 1 else 4.4)
				light.light_energy = intensity * DAYTIME_FIXTURE_SCALE
		if downlight:
			# Existing ceiling sources cover the perimeter; extra gain clips
			# the upholstery where their wide beams overlap the central lamp.
			var perimeter_output := 96.0 if int(extras.get("floor", 1)) == 3 else (72.0 if int(extras.get("floor", 1)) == 1 else 48.0)
			light.light_energy = (perimeter_output if perimeter_downlight else minf(float(source["intensity"]), 24.0)) * DAYTIME_FIXTURE_SCALE
		if general:
			# General furniture lighting belongs to the real ceiling fixtures.
			# Keep task/column sources on their local architectural receivers.
			light.light_cull_mask = _activity_light_mask(extras)
			light.set_meta("estate_fixture_boost", GENERAL_FIXTURE_BOOST)
		if general and not spot:
			# Use the existing diffuser source for soft room coverage. Restrict it
			# to interior receivers, so it cannot brighten the exterior shell.
			light.light_cull_mask = _activity_light_mask(extras)
			light.set_meta("estate_fixture_boost", OPAL_DIFFUSER_BOOST)
		mesh.add_child(light)
		light.global_position = mesh.global_transform * _vector(source["position"])
		if spot:
			var local_target := _vector(source.get("target", [0, -1, 0]))
			if pod_terrace:
				# Aim the existing parapet sources across the seating, retaining
				# their authored mounting positions and target height.
				var centre := mesh.get_aabb().get_center()
				local_target.x = centre.x
				local_target.z = centre.z
			var target := mesh.global_transform * local_target
			if perimeter_downlight and ceiling_targets.has(int(extras.get("floor", 1))):
				# Aim the existing roof-mounted source across the outward-facing
				# seating. Sloped roof normals previously sent its beam outside.
				var centre: Vector3 = ceiling_targets[int(extras.get("floor", 1))]
				target = centre.lerp(light.global_position, 0.75)
				target.y = centre.y
			if mesh.has_meta("estate_ceiling_target"):
				target = mesh.get_meta("estate_ceiling_target")
			var up := Vector3.FORWARD if absf((target - light.global_position).normalized().dot(Vector3.UP)) > 0.99 else Vector3.UP
			light.look_at(target, up)
			(light as SpotLight3D).spot_range = maxf(float(source["distance"]), 12.0) if general else float(source["distance"])
			(light as SpotLight3D).spot_angle = rad_to_deg(float(source["angle"]))
			(light as SpotLight3D).spot_attenuation = float(source.get("attenuation", 2.0))
			(light as SpotLight3D).spot_angle_attenuation = float(source.get("angle_attenuation", 1.0))
			if downlight:
				# Widen the existing downlight's beam rather than creating room
				# fills. Follow its current model mount and direction, including
				# the perimeter placements that reach the outward-facing seating.
				var beam_angle := 82.0 if int(extras.get("floor", 1)) == 3 else 75.0
				(light as SpotLight3D).spot_angle = maxf((light as SpotLight3D).spot_angle, beam_angle)
				# A softer edge reaches outward-facing furniture without raising
				# the beam's peak or introducing any additional light sources.
				(light as SpotLight3D).spot_angle_attenuation = 0.25
				if perimeter_downlight:
					# Put the beam on the perimeter rather than bathing the central
					# table again; retain every authored mounting position.
					(light as SpotLight3D).spot_angle = 55.0
					(light as SpotLight3D).spot_angle_attenuation = 0.5
			if pod_terrace:
				(light as SpotLight3D).spot_range = 6.5
				(light as SpotLight3D).spot_angle = 75.0
				(light as SpotLight3D).spot_attenuation = 1.0
				(light as SpotLight3D).spot_angle_attenuation = 0.4
			# One authored broad light per room supplies contact shadows. Other
			# local bounce lights stay unshadowed, as in the reference viewer.
			if not outdoor and not contact_rooms.has(room):
				light.shadow_enabled = true
				# Retain the existing local calibration of indoor contact sources.
				light.light_energy *= SHADOWED_PASS_SCALE
				light.shadow_caster_mask = FURNITURE_CONTACT_LAYER
				light.shadow_bias = 0.01
				light.shadow_normal_bias = 0.1
				contact_rooms[room] = true
		else:
			(light as OmniLight3D).omni_range = 14.0 if opal else (12.0 if general else float(source["distance"]))
			(light as OmniLight3D).omni_attenuation = 1.0 if general else float(source.get("attenuation", 2.0))
		light.set_meta("asset_role", "authored-daylight-fixture")


static func _vector(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))
