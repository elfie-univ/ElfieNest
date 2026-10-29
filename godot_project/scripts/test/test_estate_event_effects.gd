extends SceneTree


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var script := load("res://runtime/lab/estate_event_effects.gd") as GDScript
	if not _require(script != null, "Local event effect candidate is missing"):
		return
	var effects = script.new()
	root.add_child(effects)
	effects.configure_bed(Transform3D.IDENTITY, AABB(Vector3(-0.5, 0.5, -1.0), Vector3(1.0, 0.1, 2.0)))
	if not _check_capsule(effects):
		return
	if OS.get_environment("ELFIENEST_CAPSULE_ONLY") == "1":
		effects.free()
		print("PASS: continuous upper capsule covers the full shell in its own bed frame")
		quit(0)
		return
	effects.configure_arrival(Vector3(0, 9.92, 0), 1.1)
	effects.preview_cover(0.0)
	var dome := effects.get_node("BedEffect/GlassDome") as MeshInstance3D
	var indicator := effects.get_node("BedEffect/BedsideIndicator") as MeshInstance3D
	if not _require(not dome.visible and not indicator.visible, "Idle preview left cover or state indicator visible"):
		return
	effects.preview_cover(0.5)
	if not _check_cover_material(dome):
		return
	var material := dome.material_override as ShaderMaterial
	if not _require(dome.visible and float(material.get_shader_parameter("cover_level")) > 0.0 and float(material.get_shader_parameter("cover_level")) < 1.0, "Cover arc material did not fade in"):
		return
	effects.preview_cover(4.5)
	if not _require(dome.visible and float(material.get_shader_parameter("cover_level")) > 0.0 and float(material.get_shader_parameter("cover_level")) < 1.0, "Cover arc material did not fade out"):
		return
	effects.preview_cover(2.0)
	if not _require(indicator.visible and is_equal_approx(float(material.get_shader_parameter("cover_level")), 1.0), "Cover arc material did not hold at its full candidate level"):
		return
	if not _check_cover_pulse(effects):
		return
	effects.preview_arrival(0.5)
	var ring := effects.get_node("ArrivalEffect/ArrivalRing") as MeshInstance3D
	var beam := effects.get_node("ArrivalEffect/ArrivalBeam") as MeshInstance3D
	if not _require(ring.visible and not beam.visible and dome.visible, "Arrival warmup skipped or changed the bed effect"):
		return
	effects.preview_arrival(2.0)
	if not _require(beam.visible and is_equal_approx(effects.get_node("ArrivalEffect").global_position.y, 9.92), "Arrival candidate is detached from its real anchor or has no arrival phase"):
		return
	effects.preview_arrival(4.5)
	effects.preview_cover(5.5)
	if not _require(not ring.visible and not beam.visible and not dome.visible and not indicator.visible, "Preview effects did not dissipate completely"):
		return
	effects.preview_cover(2.0)
	effects.preview_arrival(2.0)
	effects.cancel_preview()
	if not _require(not ring.visible and not beam.visible and not dome.visible and not indicator.visible, "Cancelled preview left residual effects"):
		return
	effects.free()
	var review_script := load("res://runtime/lab/estate_event_review.gd") as GDScript
	if not _require(review_script != null, "Real-asset event review assembly is missing"):
		return
	var review = review_script.new()
	root.add_child(review)
	if not _require(review.views.size() == 5 and review.views.filter(func(view: Dictionary) -> bool: return view["id"]=="C04-exterior").is_empty() and review.counts.get("bed_module", "") == "M01" and review.counts.get("arrival_anchor", "") == "central-04/activity", "Review did not use the real M01 bed and central arrival anchor"):
		return
	var lighting := preload("res://rooms/estate/estate_lighting.gd")
	for light: Light3D in review.review_geometry.find_children("*", "Light3D", true, false):
		if lighting.is_ordinary_light(light, review.review_geometry) and not _require(not light.visible, "Daytime effect review left an ordinary fixture lit"):
			return
	var floor_mesh: Array = review.review_geometry.find_children("*", "MeshInstance3D", true, false).filter(func(mesh: MeshInstance3D) -> bool: return str((mesh.get_meta("extras", {}) as Dictionary).get("source_name", "")).contains("continuous lower floor"))
	if not _require(not floor_mesh.is_empty(), "Real room floor is missing from event review"):
		return
	var floor_bounds: AABB = floor_mesh[0].global_transform * floor_mesh[0].get_aabb()
	var camera_position: Vector3 = review.views[0]["camera"]
	if not _require(camera_position.x >= floor_bounds.position.x and camera_position.x <= floor_bounds.end.x and camera_position.z >= floor_bounds.position.z and camera_position.z <= floor_bounds.end.z, "Bed review camera is outside the real room footprint"):
		return
	var platforms: Array = review.review_geometry.find_children("*", "MeshInstance3D", true, false).filter(func(mesh: MeshInstance3D) -> bool: return str(mesh.name).begins_with("Roof01 complete raised landing platform"))
	if not _require(platforms.size() == 1, "Real raised arrival platform is missing"):
		return
	var platform_bounds: AABB = platforms[0].global_transform * platforms[0].get_aabb()
	if not _require(review.effects.get_node("ArrivalEffect").global_position.y > platform_bounds.end.y, "Arrival ring is hidden below the real raised platform surface"):
		return
	if not _check_real_shell(review) or not _check_arrival_copies(review) or not _check_arrival_camera(review):
		return
	if not _check_sleeping_fixture(review):
		return
	for view_id: String in ["sleep-back", "sleep-left", "sleep-right", "C04-arrival"]:
		review.sample_cover_view(view_id,2.6)
		if not _require(not review.effects.get_node("BedEffect/GlassDome").visible and not review.effects.get_node("BedEffect/BedsideIndicator").visible, "Ordinary sleep or arrival incorrectly enables the robot embodiment canopy"):
			return
	review.sample_cover_view("C02-bed-cover",2.6)
	if not _require(review.effects.get_node("BedEffect/GlassDome").visible, "Explicit external-body review lost its canopy"):
		return

	var held_materials: Array[Material] = []
	for binding: Dictionary in review.arrival_materials:
		held_materials.append(binding["material"])
		held_materials.append(binding.get("source"))
	review.queue_free()
	await process_frame
	held_materials.clear()
	print("PASS: local cover/indicator and arrival candidates fade, hold, clear and bind real asset sources without a world authority")
	quit(0)


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false


func _check_capsule(effects: Node3D) -> bool:
	var cover := effects.get_node("BedEffect/GlassDome") as MeshInstance3D
	if not _require(cover.mesh is ArrayMesh, "Bed cover must be a generated half capsule with straight barrel and rounded ends"):
		return false
	var bounds := cover.transform * cover.get_aabb()
	if not _require(bounds.position.x <= -0.5 and bounds.end.x >= 0.5 and bounds.position.z <= -1.0 and bounds.end.z >= 1.0 and absf(bounds.position.y - 0.6) <= 0.025, "Capsule does not cover the complete shell or meet its upper edge"):
		return false
	if not _require(not effects.has_node("BedEffect/CoverRim"), "Rejected luminous perimeter ring remains on the capsule"):
		return false
	var vertices: PackedVector3Array = cover.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var middle_width := 0.0
	var barrel_width := 0.0
	for vertex: Vector3 in vertices:
		if absf(vertex.z) < 0.01:
			middle_width = maxf(middle_width, absf(vertex.x))
		if absf(absf(vertex.z) - 0.25) < 0.015:
			barrel_width = maxf(barrel_width, absf(vertex.x))
	return _require(middle_width > 0.45 and is_equal_approx(middle_width, barrel_width), "Cover is a scaled ellipse rather than a constant-width capsule barrel")


func _check_real_shell(review: Node3D) -> bool:
	var parts: Array = review.review_geometry.find_children("*", "MeshInstance3D", true, false).filter(func(mesh: MeshInstance3D) -> bool:
		var extras := mesh.get_meta("extras", {}) as Dictionary
		return extras.get("module", "") == "M01" and extras.get("resident", "") == "A" and extras.get("assembly", "") == "bed" and extras.get("piece", "") in ["shell", "rolled_lip", "deck"])
	if not _require(parts.size() == 3 and review.counts.get("bed_shell_parts", 0) == 3, "Cover assembly does not use all three actual bed shell parts"):
		return false
	var bed := review.effects.get_node("BedEffect") as Node3D
	var cover := bed.get_node("GlassDome") as MeshInstance3D
	var cover_bounds := cover.transform * cover.get_aabb()
	var shell: MeshInstance3D = parts.filter(func(part: MeshInstance3D) -> bool: return (part.get_meta("extras", {}) as Dictionary).get("piece", "") == "shell")[0]
	if not _require(bed.global_transform.is_equal_approx(shell.global_transform), "Capsule orientation does not follow the actual authored bed frame"):
		return false
	var crown: MeshInstance3D = parts.filter(func(part: MeshInstance3D) -> bool: return (part.get_meta("extras", {}) as Dictionary).get("piece", "") == "rolled_lip")[0]
	# The user requested the cover meet the upper silver rim. The lower pod
	# skirt flares 9.1cm past this rim at each end and remains below the cover.
	# Check the full upper rim as well as the bidirectional 3cm contour checks.
	var crown_bounds := bed.global_transform.affine_inverse() * crown.global_transform * crown.get_aabb()
	if not _require(cover_bounds.position.x <= crown_bounds.position.x and cover_bounds.end.x >= crown_bounds.end.x and cover_bounds.position.z <= crown_bounds.position.z and cover_bounds.end.z >= crown_bounds.end.z, "Cover misses part of the complete silver upper rim footprint"):
		return false
	var crown_vertices: PackedVector3Array = crown.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var cover_vertices: PackedVector3Array = cover.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var crown_projection := PackedVector2Array()
	for vertex: Vector3 in crown_vertices:
		var point: Vector3 = bed.global_transform.affine_inverse() * crown.global_transform * vertex
		crown_projection.append(Vector2(point.x, point.z))
	var rim_projection := PackedVector2Array()
	for index in range(0, cover_vertices.size(), 33):
		var point := cover.transform * cover_vertices[index]
		rim_projection.append(Vector2(point.x, point.z))
	for index in range(cover_vertices.size() - 1, -1, -33):
		var point := cover.transform * cover_vertices[index]
		rim_projection.append(Vector2(point.x, point.z))
	# Every generated semicircle has 33 vertices. Its two lower endpoints must
	# sit on the actual varying crown profile, not float at the high headboard.
	for index in range(0, cover_vertices.size(), 33):
		for endpoint in [index, index + 32]:
			var point := cover.transform * cover_vertices[endpoint]
			var nearest := INF
			var source_y := 0.0
			for vertex: Vector3 in crown_vertices:
				var local: Vector3 = bed.global_transform.affine_inverse() * crown.global_transform * vertex
				var distance := Vector2(point.x, point.z).distance_squared_to(Vector2(local.x, local.z))
				if distance < nearest:
					nearest = distance
					source_y = local.y
			if not _require(sqrt(nearest) <= 0.03, "Capsule lower edge is more than 3cm horizontally from the real silver crown"):
				return false
			if not _require(absf(point.y - source_y) <= 0.025, "Capsule lower edge floats above the actual bed crown"):
				return false
	var crown_outline := Geometry2D.convex_hull(crown_projection)
	for point: Vector2 in crown_outline:
		var nearest := INF
		for index in range(rim_projection.size()):
			var closest := Geometry2D.get_closest_point_to_segment(point, rim_projection[index], rim_projection[(index + 1) % rim_projection.size()])
			nearest = minf(nearest, point.distance_to(closest))
		if not _require(nearest <= 0.03, "Fitted cover omits part of the complete authored crown boundary"):
			return false
	review.effects.preview_cover(2.0)
	if not _check_cover_material(cover):
		return false
	if not _require(not bed.has_node("CoverRim"), "Rejected luminous top rim returned"):
		return false
	return _require(float(review.views[0].get("fov", 52.0)) >= 65.0, "Complete capsule still uses the cropped close review field of view")


func _check_arrival_copies(review: Node3D) -> bool:
	if not _require(review.arrival_materials.size()>=3,"Arrival fixture bindings are missing"):return false
	review._update_arrival_materials(0.0)
	for binding: Dictionary in review.arrival_materials:
		var source := binding.get("source") as BaseMaterial3D
		if source==null:continue
		var owned := binding["material"] as ShaderMaterial
		if not _require(owned!=null and owned.get_shader_parameter("source_albedo")==source.albedo_color and source.albedo_color==binding["source_albedo"] and is_equal_approx(source.emission_energy_multiplier,float(binding["source_energy"])),"Arrival shader lost source inputs or changed imported material"):return false
	review._update_arrival_materials(3.3)
	for binding: Dictionary in review.arrival_materials:
		var material := binding["material"] as ShaderMaterial
		var level := float(material.get_shader_parameter("light_level"))
		if str(binding["group"])!="steady" and not _require(level>0.0 and level<=float(binding["peak"])+0.001,"Arrival fixture failed its bounded pulse"):return false
	review._update_arrival_materials(9.0)
	for binding: Dictionary in review.arrival_materials:
		if not _require(is_zero_approx(float((binding["material"] as ShaderMaterial).get_shader_parameter("light_level"))),"Daytime apparatus retained idle emission"):return false
	return true


func _check_arrival_camera(review: Node3D) -> bool:
	var skylights: Array = review.review_geometry.find_children("*", "MeshInstance3D", true, false).filter(func(mesh: MeshInstance3D) -> bool: return str(mesh.name).begins_with("Central integrated shallow skylight"))
	if not _require(skylights.size() == 1, "Real source skylight is missing from arrival surroundings"):
		return false
	var skylight_bounds: AABB = skylights[0].global_transform * skylights[0].get_aabb()
	var arrival_view: Dictionary = review.views.filter(func(view: Dictionary) -> bool: return view["id"]=="C04-arrival")[0]
	var camera_position: Vector3 = arrival_view["camera"]
	var beam := review.effects.get_node("ArrivalEffect/ArrivalBeam") as MeshInstance3D
	if not _require(camera_position.y < skylight_bounds.position.y, "Arrival review camera looks through the screen-sampling skylight"):
		return false
	var target: Vector3 = arrival_view["target"]
	return _require(Vector2(target.x,target.z).distance_to(Vector2(beam.global_position.x,beam.global_position.z))<0.01 and target.y>beam.global_position.y-0.5 and target.y<beam.global_position.y+0.5,"Arrival camera does not frame the actual body/beam center")


func _check_sleeping_fixture(review: Node3D) -> bool:
	var actors := review.find_children("*", "CharacterBody3D", true, false)
	if not _require(actors.size() == 1, "Cover review needs exactly one explicitly local existing sleeping Actor"):
		return false
	var actor := actors[0] as ElfieActor
	if not _require(actor != null and actor.get_meta("local_visual_sample", false) == true and not actor.is_in_group(&"runtime_elfie_actors"), "Sleeping example can be mistaken for a world resident"):
		return false
	if not _require(actor.runtime_posture() == "sleeping" and actor.furniture_anchor_id == "dorm-01/bed-01" and actor.active_command_id.is_empty(), "Example does not use the existing real-bed sleeping pose"):
		return false
	actor._process(1.0)
	var baseline := actor.global_transform
	for seconds: float in [0.0, 0.5, 2.0, 4.5, 5.5, 2.0]:
		review.effects.preview_cover(seconds)
		if not _require(actor.visible and actor.runtime_posture() == "sleeping" and actor.global_transform.is_equal_approx(baseline), "Cover cycle removed, moved or woke the body left in bed"):
			return false
	var visual := actor.get_node("VisualRoot") as Node3D
	if not _require(absf(visual.global_basis.y.normalized().dot(Vector3.UP)) < 0.01, "Existing sleeping pose is not lying horizontally"):
		return false
	var marker := review.find_child("EstateInteractionAnchors", true, false).get_node("dorm-01__bed-01") as Marker3D
	var contact := (marker.get_meta("interaction_transform") as Transform3D).origin
	var hips := actor._furniture_hips()
	var skeleton := hips["skeleton"] as Skeleton3D
	var posed_contact := skeleton.to_global(skeleton.get_bone_global_pose(int(hips["bone"])).origin)
	return _require(posed_contact.distance_to(contact) <= 0.05, "Local sleeping body is not on the actual authored bed contact")


func _check_cover_material(dome: MeshInstance3D) -> bool:
	var material := dome.material_override as ShaderMaterial
	if not _require(material != null and material.shader != null, "Cover has no view-dependent cyan arc material"):
		return false
	if not _require(not material.shader.get_shader_uniform_list().is_empty(), "Cover arc shader failed to compile"):
		return false
	var face := float(material.get_shader_parameter("face_opacity"))
	var edge := float(material.get_shader_parameter("edge_opacity"))
	var face_glow := float(material.get_shader_parameter("face_glow"))
	var edge_glow := float(material.get_shader_parameter("edge_glow"))
	var tint: Color = material.get_shader_parameter("cover_tint")
	return _require(face >= 0.25 and face <= 0.38 and edge > face and edge <= 0.6 and face_glow > 0.0 and edge_glow > face_glow and edge_glow <= 0.4 and tint.r < 0.3 and tint.b > 0.5, "Cover arc lost its bounded cyan contour or returned to the faint/grey body overlay")

func _check_cover_pulse(effects: Node3D) -> bool:
	var dome := effects.get_node("BedEffect/GlassDome") as MeshInstance3D
	var original_mesh := dome.mesh
	var original_transform := dome.transform
	var material := dome.material_override as ShaderMaterial
	var face := float(material.get_shader_parameter("face_opacity"))
	var edge := float(material.get_shader_parameter("edge_opacity"))
	effects.preview_cover(1.0)
	var low := float(material.get_shader_parameter("edge_pulse"))
	effects.preview_cover(2.6)
	var high := float(material.get_shader_parameter("edge_pulse"))
	if not _require(low>=0.0 and high<=1.0 and high-low>0.8 and is_equal_approx(float(material.get_shader_parameter("cover_level")),1.0),"Confirmed embodiment edge pulse lost its gentle hold-state cycle"):return false
	if not _require(dome.mesh==original_mesh and dome.transform==original_transform and is_equal_approx(face,float(material.get_shader_parameter("face_opacity"))) and is_equal_approx(edge,float(material.get_shader_parameter("edge_opacity"))),"Edge pulse changed the confirmed canopy shape or transparency"):return false
	effects.preview_cover(5.5)
	if not _require(not dome.visible and is_zero_approx(float(material.get_shader_parameter("edge_pulse"))),"Inactive canopy retained embodiment pulse"):return false
	effects.preview_cover(2.0)
	return true
