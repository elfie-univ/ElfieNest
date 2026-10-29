extends RefCounted
## Presentation-only material overrides; RuntimeMode owns estate visibility.

const SURFACE := preload("res://rooms/estate/estate_water.gdshader")
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const FLOW := preload("res://rooms/estate/estate_water_flow.gdshader")
# Actual sourceGardenNode markers in the approved GLB reference these meshes.
const SOURCE_SURFACES := {
	36: ["Reference fountain water", "surface"],
	66: ["COMPLETE Short east spillway", "spillway"],
	222: ["COMPLETE Short east spillway inlet transition", "spillway"],
	243: ["COMPLETE Inset natural lake receiving under spillway", "surface"],
	258: ["COMPLETE Inset natural lake", "surface"],
}
const ANIMATION_GROUP := "Animated fountain and spillway"


static func attach(root: Node3D) -> Dictionary:
	var counts := {"surface": 0, "spillway": 0, "jet": 0, "ripple": 0, "foam": 0}
	var source_names: Dictionary = {}
	for node: Node in root.find_children("*", "", true, false):
		var extras := node.get_meta("extras", {}) as Dictionary
		var source_id := int(extras.get("sourceGardenNode", -1))
		if SOURCE_SURFACES.has(source_id):
			var entry: Array = SOURCE_SURFACES[source_id]
			source_names[entry[0]] = entry[1]
	for mesh: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		var role := str(source_names.get(str(mesh.name), ""))
		var parent := mesh.get_parent()
		var in_animation_group: bool = (parent.get_meta("extras", {}) as Dictionary).get("runtimeAddition", "") == ANIMATION_GROUP
		# The existing sidecar owns this instanced spray. Do not modify its
		# hidden template or the materials used by the restored MultiMesh.
		if str(mesh.name) == "__ELFIE_INST_GROUP_133":
			continue
		for index in range(mesh.mesh.get_surface_count()):
			var actual := mesh.get_active_material(index)
			if actual != null and actual.has_meta("estate_water_role"):
				mesh.layers = (mesh.layers & ~DAYLIGHT.OUTDOOR_LIGHT_LAYER) | DAYLIGHT.WATER_LIGHT_LAYER
				counts[str(actual.get_meta("estate_water_role"))] += 1
				continue
			# Daylight may have wrapped an opaque surface in its own shader.
			# Read the original resource without editing it or the mesh.
			var original := actual as BaseMaterial3D
			if actual is ShaderMaterial:
				original = actual.get_meta("source_material", null) as BaseMaterial3D
			if original == null:
				continue
			var surface_role := role
			if surface_role.is_empty() and in_animation_group:
				if original.albedo_texture != null:
					surface_role = "foam"
				elif original.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED:
					surface_role = "ripple"
				else:
					surface_role = "jet"
			if surface_role.is_empty():
				continue
			mesh.layers = (mesh.layers & ~DAYLIGHT.OUTDOOR_LIGHT_LAYER) | DAYLIGHT.WATER_LIGHT_LAYER
			mesh.set_surface_override_material(index, _material(original, surface_role))
			counts[surface_role] += 1
	return counts


static func _material(original: BaseMaterial3D, role: String) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.resource_name = original.resource_name
	material.set_meta("source_material", original)
	material.set_meta("estate_water_role", role)
	material.shader = SURFACE if role in ["surface", "spillway"] else FLOW
	material.set_shader_parameter("source_albedo", original.albedo_color)
	material.set_shader_parameter("source_roughness", original.roughness)
	material.set_shader_parameter("source_metallic", original.metallic)
	material.set_shader_parameter("source_specular", original.metallic_specular)
	if material.shader == SURFACE:
		var optics := original.get_meta("source_optics", {}) as Dictionary
		material.set_shader_parameter("source_clearcoat", float(optics.get("clearcoat", 0.0)))
		material.set_shader_parameter("source_coat_roughness", float(optics.get("clearcoat_roughness", 0.0)))
		material.set_shader_parameter("is_spillway", role == "spillway")
	else:
		material.set_shader_parameter("is_ripple", role == "ripple")
		material.set_shader_parameter("source_unshaded", original.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED)
		material.set_shader_parameter("use_source_texture", original.albedo_texture != null)
		if original.albedo_texture != null:
			material.set_shader_parameter("source_texture", original.albedo_texture)
	return material
