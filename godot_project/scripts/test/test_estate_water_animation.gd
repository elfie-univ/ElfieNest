extends SceneTree
## Run with the repository Godot toolchain after importing the estate once.

const WATER_PATH := "res://rooms/estate/estate_water.gd"


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
	var lake := MeshInstance3D.new()
	lake.name = "COMPLETE Inset natural lake"
	lake.mesh = PlaneMesh.new()
	lake.mesh.material = original
	lake.position = Vector3(2, 3, 4)
	fixture.add_child(lake)
	var saved_mesh := lake.mesh
	var saved_transform := lake.transform
	# Match the real integration order, including daylight's source wrapper.
	var surface := load("res://rooms/estate/estate_surface.gd")
	lake.set_surface_override_material(0, surface.make_material(original, 0.65, 0.2))
	fixture.visible = false
	var counts: Dictionary = water.attach(fixture)
	var animated := lake.get_active_material(0) as ShaderMaterial
	if not _require(counts["surface"] == 1 and animated != null, "Hidden-at-attach water cannot later animate"):
		return
	if not _require(animated.get_shader_parameter("source_albedo") == original.albedo_color and animated.get_shader_parameter("source_roughness") == original.roughness and animated.get_shader_parameter("source_metallic") == original.metallic, "Water lost source color or physical material inputs"):
		return
	if not _require(lake.mesh == saved_mesh and lake.transform == saved_transform and lake.mesh.surface_get_material(0) == original, "Animation changed geometry, transform or imported material"):
		return
	fixture.visible = true
	water.attach(fixture)
	if not _require(lake.get_active_material(0) == animated and lake.is_visible_in_tree(), "Attach is not idempotent or prevents later visibility"):
		return
	fixture.free()
	# Load only the imported model, avoiding physics, navigation and sidecar restore.
	var estate := (load("res://rooms/estate/ElfieNest-complete-final.glb") as PackedScene).instantiate() as Node3D
	root.add_child(estate)
	if not _check_spillway(estate): return
	var daylight := load("res://rooms/estate/estate_daylight.gd")
	daylight.apply(estate)
	var meshes: Dictionary = {}
	var transforms: Dictionary = {}
	var previous: Dictionary = {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		meshes[mesh] = mesh.mesh
		transforms[mesh] = mesh.transform
		previous[mesh] = mesh.get_active_material(0)
	counts = water.attach(estate)
	var channel := estate.find_child("COMPLETE Short east spillway", true, false) as MeshInstance3D
	var bed := estate.find_child("CY R001 spillway sealed trough bed", true, false) as MeshInstance3D
	var channel_material := channel.get_active_material(0) as ShaderMaterial
	var bed_material := bed.get_active_material(0) as ShaderMaterial
	if not _require(channel_material != null and channel_material.shader.code.contains("ALPHA"), "Shallow channel water does not reveal its existing bed"): return
	if not _require(bed_material != null and bed_material.get_meta("estate_shallow_bed", false), "Real channel bed lacks the pebble finish"): return
	if not _require(counts == {"surface": 3, "spillway": 1, "jet": 11, "ripple": 9, "foam": 1}, "Actual source water inventory changed: " + str(counts)):
		return
	var changed := 0
	for mesh: MeshInstance3D in meshes:
		if not _require(mesh.mesh == meshes[mesh] and mesh.transform == transforms[mesh], "Source mesh or transform changed"):
			return
		if mesh.get_active_material(0) == previous[mesh]:
			continue
		changed += 1
		var material := mesh.get_active_material(0) as ShaderMaterial
		if not _require(material != null and not material.shader.get_shader_uniform_list().is_empty(), "Water shader failed to compile"):
			return
		# The importer/daylight may supply a calibrated override (for example
		# spray opacity). Compare the actual input handed to water.attach.
		var input := previous[mesh] as Material
		var source := input as BaseMaterial3D
		if input is ShaderMaterial:
			source = input.get_meta("source_material") as BaseMaterial3D
		if not _require(material.get_shader_parameter("source_albedo") == source.albedo_color and material.get_shader_parameter("source_roughness") == source.roughness, "Actual source water appearance inputs changed"):
			return
	if not _require(changed == 26, "Unexpected material changes outside water and its shallow bed"):
		return
	water.attach(estate)
	estate.free()
	print("PASS: 25 metadata-bound water surfaces; source geometry/color retained; hidden attach and repeat attach supported")
	quit(0)


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
	var layout := load("res://rooms/estate/estate_outdoor_lighting.scn").instantiate() as Node3D
	var rim: PackedVector3Array = layout.get_meta("fountain_rim")
	var pool := estate.find_child("Reference fountain water", true, false) as MeshInstance3D
	var expected := preload("res://scripts/tools/outdoor_lighting_geometry.gd").fountain_rim(estate, pool, coping)
	var matches := rim.size() == expected.size()
	if matches:
		for i in range(rim.size()):
			matches = matches and rim[i].distance_to(expected[i]) < 0.001
	var open := rim[0].distance_to(rim[-1]) > 2.0
	layout.free()
	return _require(matches and open, "Baked rim must hug the coping and leave the channel mouth open")
