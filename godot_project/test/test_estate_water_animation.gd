extends SceneTree
## Run with the repository Godot toolchain after importing the estate once.

const WATER_PATH := "res://nest/courtyard/parts/waterside/estate_water.gd"


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	if not _require(ResourceLoader.exists(WATER_PATH), "Estate water attach implementation is missing"):
		return
	var water = load(WATER_PATH)
	var fixture := Node3D.new()
	root.add_child(fixture)
	var marker := Node3D.new()
	marker.set_meta("extras", {"sourceGardenNode": 258})
	fixture.add_child(marker)
	var original := StandardMaterial3D.new()
	original.albedo_color = Color(0.32, 0.48, 0.49, 1.0)
	original.roughness = 0.22
	original.metallic = 0.02
	original.set_meta("source_optics", {"clearcoat": 0.65, "clearcoat_roughness": 0.2})
	var fixture_lake := MeshInstance3D.new()
	fixture_lake.name = "COMPLETE Inset natural lake"
	fixture_lake.mesh = PlaneMesh.new()
	fixture_lake.mesh.material = original
	fixture_lake.position = Vector3(2, 3, 4)
	fixture.add_child(fixture_lake)
	var saved_mesh := fixture_lake.mesh
	var saved_transform := fixture_lake.transform
	# Match the real integration order, including daylight's source wrapper.
	var surface_adapter := load("res://nest/rendering/estate_surface.gd")
	fixture_lake.set_surface_override_material(0, surface_adapter.make_material(original, 0.65, 0.2))
	fixture.visible = false
	var counts: Dictionary = water.attach(fixture)
	var animated := fixture_lake.get_active_material(0) as ShaderMaterial
	if not _require(counts["surface"] == 1 and animated != null, "Hidden-at-attach water cannot later animate"):
		return
	if not _require(animated.get_shader_parameter("source_albedo") == original.albedo_color and animated.get_shader_parameter("source_roughness") == original.roughness and animated.get_shader_parameter("source_metallic") == original.metallic, "Water lost source color or physical material inputs"):
		return
	if not _require(fixture_lake.mesh == saved_mesh and fixture_lake.transform == saved_transform and fixture_lake.mesh.surface_get_material(0) == original, "Animation changed geometry, transform or imported material"):
		return
	fixture.visible = true
	water.attach(fixture)
	if not _require(fixture_lake.get_active_material(0) == animated and fixture_lake.is_visible_in_tree(), "Attach is not idempotent or prevents later visibility"):
		return
	fixture.free()
	# Load the placed split scene; it restores names/extras without building physics.
	var estate := (load("res://nest/assembly/estate.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(estate)
	if not _check_spillway(estate): return
	# Formal SCNs already own the approved daylight/water materials. Snapshot
	# every surface; attach must preserve them rather than redo raw GLB setup.
	var before := _water_inventory(estate)
	if not _check_water_inventory(before): return
	var snapshots := {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		var materials: Array[Material] = []
		var signatures: Array[Dictionary] = []
		for surface: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface)
			materials.append(material)
			signatures.append(_water_material_signature(material))
		snapshots[mesh] = {"mesh": mesh.mesh, "frame": mesh.global_transform, "materials": materials, "signatures": signatures}
	for pass_index: int in 2:
		counts = water.attach(estate)
		if not _require(counts == before.counts and _water_inventory(estate) == before, "Repeated water attach changed the formal role inventory: " + str(counts)): return
		for mesh: MeshInstance3D in snapshots:
			var saved: Dictionary = snapshots[mesh]
			if not _require(mesh.mesh == saved.mesh and mesh.global_transform == saved.frame, "Water attach changed formal mesh geometry or world placement: " + str(mesh.name)): return
			for surface: int in mesh.mesh.get_surface_count():
				var actual := mesh.get_active_material(surface)
				if not _require(actual == saved.materials[surface] and _water_material_signature(actual) == saved.signatures[surface], "Water attach changed an existing material, role or authored source input: %s surface=%d pass=%d" % [mesh.name, surface, pass_index]): return
	var channel := estate.find_child("COMPLETE Short east spillway", true, false) as MeshInstance3D
	var bed := estate.find_child("CY R001 spillway sealed trough bed", true, false) as MeshInstance3D
	var channel_material := channel.get_active_material(0) as ShaderMaterial
	var bed_material := bed.get_active_material(0) as ShaderMaterial
	if not _require(channel_material != null and channel_material.shader.code.contains("ALPHA"), "Shallow channel water does not reveal its existing bed"): return
	if not _require(bed_material != null and bed_material.get_meta("estate_shallow_bed", false), "Real channel bed lacks the pebble finish"): return
	var source_rim := estate.find_child("FountainConcealedRim", true, false) as MeshInstance3D
	var shared_rim := source_rim.mesh
	var shared_faces := shared_rim.get_faces().to_byte_array()
	var display := preload("res://nest/courtyard/parts/waterside/estate_water_display.gd").new()
	root.add_child(display)
	display.bind(estate)
	if not _require(source_rim.mesh == shared_rim and source_rim.mesh.get_faces().to_byte_array() == shared_faces, "Binding imported water must not rebuild or mutate the shared rim prototype"): return
	if not _check_bound_rim(estate, display): return
	var lake := estate.find_child("COMPLETE Inset natural lake", true, false) as MeshInstance3D
	var fall := estate.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
	var lake_material := lake.get_active_material(0) as ShaderMaterial
	var fall_material := fall.get_active_material(0) as ShaderMaterial
	display.sample(1.0, false)
	var lake_time: float = lake_material.get_shader_parameter("presentation_time")
	var fall_phase: float = fall_material.get_shader_parameter("waterfall_phase")
	display.sample(2.0, true)
	if not _require(float(lake_material.get_shader_parameter("presentation_time")) > lake_time and float(fall_material.get_shader_parameter("waterfall_phase")) > fall_phase, "Real DISPLAY sampling must advance the existing lake and waterfall materials"): return
	if not _require(float(fall_material.get_shader_parameter("waterfall_glow")) > 0.0, "Real waterfall night illumination is missing"): return
	display.sample(3.0, false)
	if not _require(is_zero_approx(float(fall_material.get_shader_parameter("waterfall_glow"))), "Real waterfall night illumination must switch off by day"): return
	display.free()
	estate.free()
	print("PASS formal water inventory: ", before.counts, "; existing materials/geometry/source inputs retained; hidden/repeated attach and real DISPLAY sampling supported")
	quit(0)


func _water_inventory(estate: Node3D) -> Dictionary:
	var counts := {"surface": 0, "spillway": 0, "jet": 0, "ripple": 0, "foam": 0}
	var members := {"surface": [], "spillway": [], "jet": [], "ripple": [], "foam": []}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		for surface: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface)
			if material == null or not material.has_meta("estate_water_role"): continue
			var role := str(material.get_meta("estate_water_role"))
			if not counts.has(role):
				counts[role] = 0
				members[role] = []
			counts[role] += 1
			members[role].append({"name": str(mesh.name), "surface": surface, "path": str(estate.get_path_to(mesh)), "source": str(mesh.get_meta("v044_path", ""))})
	return {"counts": counts, "members": members}


func _check_water_inventory(inventory: Dictionary) -> bool:
	for role: String in inventory.members:
		print("WATER_ROLE role=", role, " count=", inventory.counts[role], " members=", JSON.stringify(inventory.members[role]))
	var surfaces: Array[String] = []
	for member: Dictionary in inventory.members.surface: surfaces.append(member.name)
	surfaces.sort()
	var expected: Array[String] = ["COMPLETE Inset natural lake", "COMPLETE Inset natural lake receiving under spillway", "Reference fountain water"]
	expected.sort()
	if not _require(surfaces == expected, "Formal surface inventory must contain the lake, receiving surface and fountain pool exactly once: " + str(surfaces)): return false
	if not _require(inventory.members.spillway.size() == 1 and inventory.members.spillway[0].name == "COMPLETE Short east spillway", "The channel must retain its separate shallow spillway role"): return false
	# Counts measured on the approved formal assembly, including its saved jets.
	return _require(inventory.counts == {"surface": 3, "spillway": 1, "jet": 28, "ripple": 9, "foam": 1}, "Formal rendered water-role inventory changed: " + str(inventory.counts))


func _water_material_signature(material: Material) -> Dictionary:
	if material == null: return {}
	var has_source: bool = material.has_meta("source_material")
	var result: Dictionary = {"role": material.get_meta("estate_water_role", ""), "has_source": has_source}
	# Godot reports missing metadata when the default is null. Preserve absence
	# explicitly; calibrated saved materials need not retain a source wrapper.
	if has_source: result["source"] = material.get_meta("source_material")
	if material is ShaderMaterial and material.has_meta("estate_water_role"):
		result.shader = material.shader
		for parameter: String in ["source_albedo", "source_roughness", "source_metallic", "source_specular"]:
			result[parameter] = material.get_shader_parameter(parameter)
	return result


func _require(condition: bool, message: String) -> bool:
	if not condition:
		push_error(message)
		quit(1)
	return condition


func _check_spillway(estate: Node3D) -> bool:
	var coping := estate.find_child("ROAD REF • fountain radial limestone coping", true, false) as MeshInstance3D
	var top := (coping.global_transform * coping.get_aabb()).end.y
	for side: String in ["north", "south"]:
		var wall := estate.find_child("CY R001 spillway %s continuous side wall" % side, true, false) as MeshInstance3D
		var bounds := wall.global_transform * wall.get_aabb()
		if not _require(absf(bounds.end.y - top) < 0.001, "Channel wall must meet coping without a step"): return false
		if not _require(absf(bounds.size.z - 0.28) < 0.001, "Keep the approved slender channel walls"): return false
	if not _require(estate.find_child("COMPLETE Short east spillway inlet transition", true, false) == null, "Remove the overlapping inlet patch, not just its color"): return false
	var channel := estate.find_child("COMPLETE Short east spillway", true, false) as MeshInstance3D
	var pool_mesh := estate.find_child("Reference fountain water", true, false) as MeshInstance3D
	var pool_faces := pool_mesh.mesh.get_faces()
	# Compare both imported surfaces; packed normals have quantization error.
	var pool_normal := (pool_mesh.global_basis * (pool_mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_NORMAL] as PackedVector3Array)[0]).normalized()
	if not _require(pool_normal.y > 0.99, "Pool normals must face upward alongside the channel"): return false
	var channel_arrays := channel.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = channel_arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = channel_arrays[Mesh.ARRAY_NORMAL]
	# Imported positions are quantized independently within each mesh AABB.
	var seam_tolerance := 2.0 * (pool_mesh.get_aabb().size.length() + channel.get_aabb().size.length()) / 65535.0
	var seam_count := 0
	for i in range(vertices.size()):
		var point := channel.global_transform * vertices[i]
		var normal := (channel.global_basis * normals[i]).normalized()
		if not _require(normal.y > 0.99, "Channel normals must face upward, matching the shallow water"): return false
		var boundary := -INF
		for face in range(0, pool_faces.size(), 3):
			for edge in range(3):
				var a := pool_mesh.global_transform * pool_faces[face + edge]
				var b := pool_mesh.global_transform * pool_faces[face + (edge + 1) % 3]
				if absf(a.z-b.z) < 0.000001 or point.z < minf(a.z,b.z)-0.000001 or point.z > maxf(a.z,b.z)+0.000001: continue
				boundary = maxf(boundary, lerpf(a.x,b.x,(point.z-a.z)/(b.z-a.z)))
		if not _require(is_finite(boundary) and point.x >= boundary-seam_tolerance, "Channel must not overlap the pool"): return false
		if absf(point.x-boundary) < seam_tolerance:
			seam_count += 1
			if not _require(absf(point.y-0.48)<0.00001 and normal.distance_to(pool_normal)<0.00001, "Shared seam must have matching height and normals"): return false
	if not _require(seam_count >= 4, "Channel must follow the curved pool boundary without a rectangular patch"): return false
	var fall := estate.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
	if not _require((fall.global_transform * fall.get_aabb()).size.y > 0.8, "Keep the final waterfall into the lake"): return false
	return true


func _check_bound_rim(estate: Node3D, display: Node3D) -> bool:
	# The approved rim already carries mitred ends. Check the production join
	# after DISPLAY binds it, rather than comparing to an unmitred fresh strip.
	const TOLERANCE := 0.001
	var rim := estate.find_child("FountainConcealedRim", true, false) as MeshInstance3D
	if not _require(rim != null and rim.mesh != null, "Regional fountain rim is missing"): return false
	var faces := rim.mesh.get_faces()
	for index: int in faces.size(): faces[index] = rim.global_transform * faces[index]
	var seams: Array[Vector3] = []
	var centers: Array[Vector3] = []
	var strips := display.find_children("SpillwayEdge*", "MeshInstance3D", true, false)
	if not _require(strips.size() == 2, "Bound rim needs both actual spillway guides"): return false
	for strip: MeshInstance3D in strips:
		var points: PackedVector3Array = strip.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		if not _require(points.size() >= 16 and (points.size() - 12) % 2 == 0, "Bound guide lost its body pairs and rounded nose"): return false
		var a := strip.global_transform * points[0]
		var b := strip.global_transform * points[1]
		seams.append(a)
		seams.append(b)
		centers.append((a+b)*0.5)
		var seam_error := INF
		for start: int in range(0, faces.size(), 3):
			for edge: int in 3:
				var first := faces[start + edge]
				var second := faces[start + (edge+1)%3]
				seam_error = minf(seam_error, minf(maxf(a.distance_to(first), b.distance_to(second)), maxf(a.distance_to(second), b.distance_to(first))))
		print("RIM_JOIN strip=", strip.name, " seam_error=", seam_error, " tolerance=", TOLERANCE)
		if not _require(seam_error <= TOLERANCE, "Both rendered rim borders must meet the actual guide inlet"): return false
		for index: int in range(0, points.size()-12, 2):
			var first := strip.global_transform * points[index]
			var second := strip.global_transform * points[index+1]
			if not _require(absf(absf(second.z-first.z)-0.10) <= TOLERANCE, "Bound channel guides must retain their 10 cm world width"): return false
	var pool := estate.find_child("Reference fountain water", true, false) as MeshInstance3D
	var coping := estate.find_child("ROAD REF • fountain radial limestone coping", true, false) as MeshInstance3D
	var centerline := preload("res://tools/outdoor_lighting_geometry.gd").fountain_rim(estate, pool, coping)
	var maximum_error := 0.0
	for point: Vector3 in faces:
		var joint := false
		for seam: Vector3 in seams: joint = joint or point.distance_to(seam) <= TOLERANCE
		if joint: continue
		var distance := INF
		for index: int in range(centerline.size()-1):
			distance = minf(distance, point.distance_to(Geometry3D.get_closest_point_to_segment(point, centerline[index], centerline[index+1])))
		var error := absf(distance-0.05)
		maximum_error = maxf(maximum_error, error)
		if not _require(error <= TOLERANCE, "Rendered rim border left its 5 cm coping offset: point=%s error=%f" % [point, error]): return false
		if not _require(absf(point.y-centerline[0].y) <= TOLERANCE, "Rendered rim lost its actual coping elevation"): return false
	# Only the middle arc keeps the unmitred reference centerline. The first
	# and last segments were replaced by the production miter; their two real
	# borders are checked against the actual guide inlets above, at TOLERANCE.
	if not _require(centerline.size() >= 4, "Rim must retain a measurable middle arc"): return false
	for index: int in range(1, centerline.size()-2):
		var point := (centerline[index]+centerline[index+1])*0.5
		if not _require(_rim_covers(faces, point, TOLERANCE), "Rendered fountain rim has an uncovered coping segment: %d" % index): return false
	var opening := (centers[0]+centers[1])*0.5
	var gap := centers[0].distance_to(centers[1])
	print("RIM_GEOMETRY faces=", faces.size()/3, " maximum_border_error=", maximum_error, " midarc_segments=", centerline.size()-3, " miter_segments=2 opening=", gap, " tolerance=", TOLERANCE)
	return _require(gap > 2.0 and not _rim_covers(faces, opening, TOLERANCE), "Actual rim must leave the channel mouth open")


func _rim_covers(faces: PackedVector3Array, point: Vector3, tolerance: float) -> bool:
	for start: int in range(0, faces.size(), 3):
		var hit: Variant = Geometry3D.segment_intersects_triangle(point+Vector3.UP*0.02, point-Vector3.UP*0.02, faces[start], faces[start+1], faces[start+2])
		if hit is Vector3 and point.distance_to(hit) <= tolerance: return true
	return false
