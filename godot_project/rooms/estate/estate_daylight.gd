extends RefCounted
## Rendering-only daylight calibration; the imported asset stays untouched.

const SURFACE := preload("res://rooms/estate/estate_surface.gd")

# Shadowed Compatibility lights are encoded in a separate additive pass.
# Retain the sample's displayed-contrast calibration for that pass only.
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
# Separate general room lighting from tiny stair/shelf accents in Compatibility.
const ACTIVITY_LAYERS := [INTERIOR_FILL_LAYER, 1 << 16, 1 << 19]
const NIGHT_NATURAL_SCALE := 0.035
const NIGHT_EMISSION := &"estate_night_emission_energy"
# The reference's day mode runs authored fixtures at 8%. Compatibility's
# non-physical Light3D energy is multiplied by PI before the same inverse-square
# light attenuation; convert that convention rather than copying raw intensity.
const DAYTIME_FIXTURE_SCALE := 0.08 / PI
# Broad ceiling fixtures overlap; retain surface detail in the LDR renderer.
const GENERAL_FIXTURE_BOOST := 3.125
# The opal fixture's authored point source provides its broad diffuse output.
const OPAL_DIFFUSER_BOOST := 25.0
# Distinguish authored bounce from powered fixture surfaces in diagnostics.
# Both retain source emission; only tagged diffusers with actual light entries
# receive the reference viewer's daytime intensity override.
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
	var materials: Dictionary = {}
	var windows: Dictionary = {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		SURFACE.repair_window_normals(mesh, windows)
		if (mesh.get_meta("extras", {}) as Dictionary).get("piece") == "bed_cover":
			mesh.mesh = SURFACE.duvet_rest(mesh.mesh)
	preload("res://rooms/estate/estate_bedding_layers.gd").attach(estate)
	var counts := {"sun": 0, "artificial_surfaces": 0, "sky_meshes": 0, "glass_surfaces": 0, "corrected_surfaces": 0}
	_calibrate(estate, materials, counts)
	# Keep indoor/outdoor shadow masks separate while sharing the reference
	# direction and unshadowed fill units across the complete scene.
	for light: Node in estate.find_children("*", "DirectionalLight3D", true, false):
		(light as DirectionalLight3D).global_position = (estate as Node3D).to_global(Vector3(-20, 35, 24))
		(light as DirectionalLight3D).look_at((estate as Node3D).global_position)
		var outdoor_sun := (light as DirectionalLight3D).duplicate() as DirectionalLight3D
		outdoor_sun.name = "CourtyardDaylight"
		outdoor_sun.light_cull_mask = OUTDOOR_LIGHT_LAYER | LANDSCAPE_LIGHT_LAYER | WATER_LIGHT_LAYER
		outdoor_sun.light_energy = OUTDOOR_SUN_ENERGY
		outdoor_sun.light_color = Color.hex(0xffe7c3ff)
		light.get_parent().add_child(outdoor_sun)
		outdoor_sun.global_position = (estate as Node3D).to_global(Vector3(-20, 35, 24))
		outdoor_sun.look_at((estate as Node3D).global_position)
		for entry: Array in [[0xcdeaffff, 0.65, Vector3(22, 25, -24)], [0xffffffff, 0.30, Vector3(0, 15, 32)]]:
			var fill := DirectionalLight3D.new()
			fill.name = "CourtyardReferenceFillCool" if int(entry[0]) == 0xcdeaffff else "CourtyardReferenceFillFront"
			fill.light_cull_mask = INTERIOR_FILL_LAYER | OUTDOOR_LIGHT_LAYER | LANDSCAPE_LIGHT_LAYER | WATER_LIGHT_LAYER
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
	for mesh: Node in estate.find_children("*", "MeshInstance3D", true, false):
		_restore_fixture_lights(mesh as MeshInstance3D, contact_rooms)
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
		lamp.visible = false
	return counts


static func _calibrate(node: Node, materials: Dictionary, counts: Dictionary) -> void:
	if node is DirectionalLight3D:
		var sunlight := node as DirectionalLight3D
		sunlight.light_color = SUN_COLOR
		sunlight.light_energy = SUN_ENERGY
		sunlight.shadow_enabled = true
		sunlight.light_cull_mask = INTERIOR_FILL_LAYER
		counts["sun"] += 1
	elif node is Light3D:
		(node as Light3D).visible = false
	if node is MeshInstance3D:
		var instance := node as MeshInstance3D
		var extras := instance.get_meta("extras", {}) as Dictionary
		instance.layers |= _room_light_mask(extras)
		var source_name := str(extras.get("source_name", instance.name)).to_lower()
		var room_receiver := str(extras.get("module", "")) == "central" and (bool(extras.get("furniture", false)) or "floor" in source_name or "slab" in source_name)
		var room_group := "central-%02d" % clampi(int(extras.get("floor", 1)), 1, 3) if room_receiver else ""
		if room_receiver:
			# The floor and furniture reliably receive the existing general ceiling
			# fixtures, instead of spending their eight-light budget on stair LEDs.
			instance.layers &= ~_room_light_mask(extras)
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
		if instance.mesh != null:
			for surface in range(instance.mesh.get_surface_count()):
				var original := instance.get_active_material(surface) as BaseMaterial3D
				if original == null:
					continue
				var material_name := original.resource_name.to_lower()
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
				var vertex_painted := instance.mesh is ArrayMesh and bool(instance.mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR)
				var physical_surface := SURFACE.supports(original, true, room_receiver) and not _is_landscape_template(instance)
				# Rubber tree assets store leaf/wood colors in glTF COLOR_0;
				# their imported shared material does not enable vertex albedo.
				var uses_vertex_color := vertex_painted and (original.vertex_color_use_as_albedo or material_name.begins_with("rubber tree "))
				var sheen: Dictionary = optics.get("sheen", {})
				var fabric_surface := not sheen.is_empty() and original.albedo_texture == null and not original.emission_enabled and not vertex_painted and not _is_landscape_template(instance)
				if not clear_glazing and not artificial and finish.is_empty() and not diffuser and not physical_surface and not fabric_surface:
					continue
				# A shared material can belong to both a powered diffuser and an
				# unpowered decorative ring; their day intensities differ.
				var identity := "%d:%s:%s:%s" % [original.get_instance_id(), diffuser, uses_vertex_color, room_group]
				if not materials.has(identity):
					var calibrated := original.duplicate() as BaseMaterial3D
					if diffuser:
						calibrated.emission_enabled = true
						calibrated.emission_energy_multiplier = 1.0 if extras.has("outdoor_fixture_id") else 0.15
						calibrated.set_meta(NIGHT_EMISSION, 1.0)
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
	return ACTIVITY_LAYERS[clampi(int(extras.get("floor", 1)), 1, 3) - 1]


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
			return (1 << 5) | (1 << 6) | (1 << 7)
		return 1 << (4 + clampi(int(extras.get("floor", 1)), 1, 3))
	if module in ["M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08"]:
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


static func _restore_fixture_lights(mesh: MeshInstance3D, contact_rooms: Dictionary) -> void:
	var extras := mesh.get_meta("extras", {}) as Dictionary
	var room := "%s:%s" % [extras.get("module", ""), extras.get("floor", 1)]
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
		light.light_cull_mask = _room_light_mask(extras)
		var label := str(extras.get("source_name", mesh.name)).to_lower()
		var general := str(extras.get("module", "")) == "central" and ("circular opal ceiling diffuser" in label or " downlight " in label)
		if str(extras.get("module", "")) == "central" and float(source["intensity"]) >= 4.0:
			# Existing reading/column lights also serve furniture at the perimeter.
			light.light_cull_mask |= _activity_light_mask(extras)
		if general:
			light.set_meta("estate_fixture_boost", GENERAL_FIXTURE_BOOST)
		if general and not spot:
			# Use the existing diffuser source for soft room coverage. Restrict it
			# to interior receivers, so it cannot brighten the exterior shell.
			light.light_cull_mask = _activity_light_mask(extras)
			light.set_meta("estate_fixture_boost", OPAL_DIFFUSER_BOOST)
			(light as OmniLight3D).omni_attenuation = 1.0
		mesh.add_child(light)
		light.global_position = mesh.global_transform * _vector(source["position"])
		if spot:
			var target := mesh.global_transform * _vector(source.get("target", [0, -1, 0]))
			var up := Vector3.FORWARD if absf((target - light.global_position).normalized().dot(Vector3.UP)) > 0.99 else Vector3.UP
			light.look_at(target, up)
			(light as SpotLight3D).spot_range = maxf(float(source["distance"]), 12.0) if general else float(source["distance"])
			(light as SpotLight3D).spot_angle = rad_to_deg(float(source["angle"]))
			(light as SpotLight3D).spot_attenuation = float(source.get("attenuation", 2.0))
			(light as SpotLight3D).spot_angle_attenuation = float(source.get("angle_attenuation", 1.0))
			# One authored broad light per room supplies contact shadows. Other
			# local bounce lights stay unshadowed, as in the reference viewer.
			if not outdoor and not contact_rooms.has(room):
				light.shadow_enabled = true
				# Shadowed positional lights use the same encoded additive pass
				# as the sun; apply its displayed-contrast calibration too.
				light.light_energy *= SHADOWED_PASS_SCALE
				light.shadow_caster_mask = FURNITURE_CONTACT_LAYER
				light.shadow_bias = 0.01
				light.shadow_normal_bias = 0.1
				contact_rooms[room] = true
		else:
			(light as OmniLight3D).omni_range = 12.0 if general else float(source["distance"])
			(light as OmniLight3D).omni_attenuation = float(source.get("attenuation", 2.0))
		light.set_meta("asset_role", "authored-daylight-fixture")


static func _vector(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))
