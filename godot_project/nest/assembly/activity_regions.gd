@tool
extends Resource
## Activity permissions are separate from render geometry and physical obstacles.
## Every surface is evaluated from the current split placement, including height.

@export var outdoor_permissions: Dictionary = {}

func source_name(mesh: MeshInstance3D) -> String:
	var source: Dictionary = mesh.mesh.get_meta("nest_source_extras", {})
	return str(source.get("source_name", str(mesh.get_meta("v044_path", mesh.name)).get_slice("/Region_", 0).get_file()))

func module_of(node: Node) -> String:
	# Placement IDs keep the room identity even when the GLB prototype is shared.
	var placement := str(node.get_meta("v044_path", "")).get_file()
	if placement.length() >= 6 and placement.substr(3).begins_with(" | "):
		var code := placement.left(3)
		if code.begins_with("M") and code.substr(1).is_valid_int() and int(code.substr(1)) >= 1 and int(code.substr(1)) <= 8: return code
	var context := node
	while context != null:
		if context.has_meta("estate_module"): return str(context.get_meta("estate_module"))
		# Building-layout instances already have stable M01–M08 identities.
		# The shared pod's source names all say M01 and cannot identify its owner.
		var identity := str(context.name)
		if identity.length() == 3 and identity.begins_with("M") and identity.substr(1).is_valid_int():
			var ordinal := int(identity.substr(1))
			if ordinal >= 1 and ordinal <= 8: return identity
		context = context.get_parent()
	return ""

func zone_for(mesh: MeshInstance3D) -> String:
	var source := source_name(mesh)
	var module := module_of(mesh)
	if source.begins_with("COMPLETE Building garden island"): return "lawn"
	if source.begins_with("Central L1 fitted complete floor"): return "central-01"
	if source.begins_with("Central L2 complete slab"): return "central-02"
	if source.begins_with("Central L3 complete slab"): return "central-03"
	if source.begins_with("Central L4 round arrival floor") or source.begins_with("Roof01 complete raised landing platform") or source.begins_with("Roof01 two rear fan steps"): return "central-04"
	if source.begins_with("Public stair") and " tread " in source: return "stairs"
	if "STAIR • half landing" in source or "STAIR • solid flight" in source: return "stairs"
	if "flush threshold" in source or "CONNECTOR • sealed landing and arch" in source: return "thresholds"
	if source == "Central L1 rounded garden entrance": return "thresholds"
	if "continuous lower floor" in source and module.begins_with("M"): return "dorm-%02d" % int(module.trim_prefix("M"))
	if "inset terrace walking finish" in source and module.begins_with("M"): return "terrace-%02d" % int(module.trim_prefix("M"))
	if source.begins_with("ROAD REF • ring ") or source.begins_with("Flower preview |") or source.begins_with("FOREST TRAIL smooth gravel") or source == "CY R003 circular waterfront platform closed foundation" or source.begins_with("Lake inlay reference gold frame") or source == "Fountain connector paving foundation": return "courtyard"
	return ""

func collect_surfaces(estate: Node3D) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or mesh.has_meta("source_geometry_path"): continue
		var zone := zone_for(mesh)
		if not zone.is_empty(): result.append({"zone": zone, "mesh": mesh, "source": source_name(mesh)})
	return result

func permission_rings(role: String) -> Array[PackedVector2Array]:
	var result: Array[PackedVector2Array] = []
	for data: Dictionary in outdoor_permissions.get(role, []):
		var ring := PackedVector2Array()
		for point: Array in data.points: ring.append(Vector2(point[0], point[1]))
		# Preserve outer/hole winding; permission polygons contain no render mesh.
		if Geometry2D.is_polygon_clockwise(ring) != bool(data.hole): ring.reverse()
		result.append(ring)
	return result

func populate_outdoor(access: Node3D, estate: Node3D) -> bool:
	if not outdoor_permissions.has("lawn") or not outdoor_permissions.has("planting"): return false
	access._add_surface(permission_rings("lawn"), access._lawns)
	access._add_surface(permission_rings("planting"), access._lawn_exclusions)
	access._add_surface(permission_rings("woodland"), access._lawn_exclusions)
	for item: Dictionary in collect_surfaces(estate):
		if item.zone not in ["courtyard", "central-01"] and not str(item.zone).begins_with("dorm-") and item.zone != "thresholds": continue
		var mesh: MeshInstance3D = item.mesh
		if item.source == "Central L1 rounded garden entrance":
			# The real portal spans the seam between indoor slab and outdoor tread.
			var bounds := mesh.global_transform * mesh.get_aabb()
			var back := bounds.position.z - bounds.size.z
			var front := bounds.end.z + bounds.size.z
			var portal: Array[PackedVector2Array] = [PackedVector2Array([Vector2(bounds.position.x, back), Vector2(bounds.end.x, back), Vector2(bounds.end.x, front), Vector2(bounds.position.x, front)])]
			access._add_surface(portal, access._surfaces)
		# The ground-storey mask must not project upstairs rooms onto the lawn.
		if (mesh.global_transform * mesh.get_aabb()).position.y > 1.5: continue
		for surface: int in mesh.mesh.get_surface_count():
			var rings: Array[PackedVector2Array] = access._top_outlines(mesh, surface)
			if rings.is_empty(): continue
			access._add_surface(rings, access._surfaces, item.zone == "courtyard")
			if str(item.source).begins_with("ROAD REF • ring continuous"):
				for ring: PackedVector2Array in rings:
					var single: Array[PackedVector2Array] = [ring]
					access._add_surface(single, access._lawn_exclusions)
		access.source_names.append(str(item.source))
	# Water and basins follow their edited split geometry, not the old shoreline.
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or mesh.has_meta("source_geometry_path"): continue
		var source := source_name(mesh)
		if source.begins_with("COMPLETE Inset natural lake") or source.begins_with("CY R001 fountain ") or source.begins_with("CY R001 spillway "):
			for surface: int in mesh.mesh.get_surface_count():
				for ring: PackedVector2Array in access._top_outlines(mesh, surface, 0.25):
					var single: Array[PackedVector2Array] = [ring]
					access._add_surface(single, access._closed_facilities)
	return not access._surfaces.is_empty() and not access._lawns.is_empty()
